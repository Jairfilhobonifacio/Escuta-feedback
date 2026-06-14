"""Sync de clientes Bizzu (Partner API) -> Escuta: classificacao por perfil.

Pagina TODOS os clientes pela API de Clientes da Bizzu (somente leitura), classifica
cada um num PERFIL (app/domain/segmentation/profiles.py) e enriquece o contato já
existente no Escuta com perfil + campos de assinatura/nps — gravados em
`Contact.profile_data` (JSONB livre; NÃO precisa migration).

Regra create/update (idempotente, upsert manual por (org_id, phone)):
  - contato novo  -> cria com opt_in=True, nome e profile_data.partner enriquecido
  - ja existe     -> eleva opt_in se False, preenche nome se ausente (nunca sobrescreve),
                     e SEMPRE atualiza o bloco profile_data["partner"] (perfil/assinatura/nps
                     sao snapshot da API, refresca a cada sync). Copia-edita-REatribui o dict.

NUNCA dispara WhatsApp/survey em nenhum caminho - so dados + classificacao.
Por isso o default executa de verdade; use --dry-run para auditar a distribuicao.

  --dry-run  -> SO imprime a distribuicao por perfil (contagens + %) e o total.
                NAO toca o banco e NAO imprime PII (apenas numeros).

Privacidade (LGPD): sem --dry-run grava PII (nome) só no banco do próprio Escuta;
o stdout nunca imprime nome/e-mail/whatsapp — só telefone-dígitos e ids opacos.

Envs:
  DATABASE_URL          — Supabase do Escuta (postgresql+asyncpg://...), via .env
  BIZZU_PARTNER_API_URL — base da API (default https://api.bizzu.ai)
  BIZZU_PARTNER_API_KEY — segredo X-API-Key (peça ao Felipe; nunca commitar)

Uso:
    py scripts/sync_partner_customers.py --dry-run [--search TEXTO]
    py scripts/sync_partner_customers.py [--search TEXTO]
"""
from __future__ import annotations

# Fix TLS ANTES de qualquer import que abra conexão TLS (chamada HTTPS à api.bizzu.ai).
# Global por processo — espelha app/main.py e os outros scripts standalone.
import truststore

truststore.inject_into_ssl()

import argparse
import asyncio
import os
import re
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:
    pass

ORG_SLUG = "bizzu"  # org-destino no Escuta (mesma do sync_bizzu_contacts)


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _build_partner_profile(customer: dict, classification: dict) -> dict:
    """Snapshot enxuto p/ gravar em profile_data['partner'] (sem PII além do necessário).

    Guarda perfil + campos de assinatura/nps que alimentam a segmentação. Não guarda
    e-mail nem nome aqui (nome vai no campo Contact.name). id como string (JSON-safe).
    """
    sub = customer.get("subscription") or {}
    nps = customer.get("nps") or {}
    cid = customer.get("id")
    return {
        "partner_customer_id": str(cid) if cid is not None else None,
        "profile": classification["profile"],
        "profile_reason": classification["reason"],
        "should_contact": classification["should_contact"],
        "subscription": {
            "state": sub.get("state"),
            "active": sub.get("active"),
            "cancelled": sub.get("cancelled"),
            "complimentary": sub.get("complimentary"),
            "planType": sub.get("planType"),
            "cancellationReason": sub.get("cancellationReason"),
            "daysAsSubscriber": sub.get("daysAsSubscriber"),
            "currentPeriodEnd": sub.get("currentPeriodEnd"),
        },
        "nps": {
            "voted": nps.get("voted"),
            "score": nps.get("score"),
            "respondedAt": nps.get("respondedAt"),
        },
    }


async def sync(dry_run: bool, search: str) -> int:
    from app.domain.segmentation.profiles import classify_profile
    from app.integrations.bizzu_partner import BizzuPartnerClient, BizzuPartnerError

    # --- 1. Paginar + classificar (sempre, inclusive em dry-run) ---
    client = BizzuPartnerClient()
    customers: list[dict] = []
    try:
        async for c in client.iter_all_customers(search=search):
            customers.append(c)
    except BizzuPartnerError as exc:
        print(f"ERRO: API de Clientes da Bizzu falhou ({exc}).", file=sys.stderr)
        return 1

    print(f"Partner: {len(customers)} cliente(s) retornado(s) pela API")

    # Distribuição por perfil (só números — sem PII).
    dist: dict[str, int] = {}
    classified: list[tuple[dict, dict]] = []
    for c in customers:
        cls = classify_profile(c)
        classified.append((c, cls))
        dist[cls["profile"]] = dist.get(cls["profile"], 0) + 1

    total = len(classified)
    print("=== Distribuição por perfil ===")
    for profile, count in sorted(dist.items(), key=lambda kv: kv[1], reverse=True):
        pct = (count / total * 100) if total else 0.0
        print(f"  {profile:<20} {count:>5}  ({pct:5.1f}%)")
    print(f"  {'TOTAL':<20} {total:>5}")

    if dry_run:
        print("=== DRY-RUN (nada gravado, sem tocar o banco) ===")
        return 0

    # --- 2. Upsert no Escuta (só fora do dry-run) ---
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.core import Contact, Organization
    import app.models.feedback  # noqa: F401  registra feedback_items no metadata
    import app.models.improvement  # noqa: F401  FK feedback_items.improvement_id -> improvements
    import app.models.survey  # noqa: F401  mapeamentos completos (evita NoReferencedTableError)
    from app.domain.feedback.ingest import ingest_feedback_item
    from app.domain.feedback.partner_map import partner_feedback_specs

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada (Supabase do Escuta).", file=sys.stderr)
        return 1

    created = updated = unchanged = invalid = skipped = 0
    fb_items = 0
    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.slug == ORG_SLUG))
        ).scalar_one_or_none()
        if org is None:
            print(f"ERRO: org '{ORG_SLUG}' não existe no Escuta (rode o seed).", file=sys.stderr)
            return 1

        for customer, classification in classified:
            partner = _build_partner_profile(customer, classification)
            partner_id = partner["partner_customer_id"]
            phone = _digits_only(customer.get("whatsapp") or "")
            name = (customer.get("name") or "").strip() or None

            if len(phone) < 10:
                invalid += 1
                # Sem PII no log: só id opaco + perfil.
                print(f"  ~ sem whatsapp válido, pulado: id={partner_id} perfil={partner['profile']}")
                continue

            contact = (
                await session.execute(
                    select(Contact).where(
                        Contact.organization_id == org.id, Contact.phone == phone
                    )
                )
            ).scalar_one_or_none()

            if contact is None:
                created += 1
                print(f"  + criar {phone} perfil={partner['profile']}")
                contact = Contact(
                    organization_id=org.id,
                    phone=phone,
                    name=name,
                    opt_in=True,
                    profile_data={"partner_customer_id": partner_id, "partner": partner},
                )
                session.add(contact)
                await session.flush()  # garante contact.id p/ vincular os FeedbackItems
            else:
                changes: list[str] = []
                if not contact.opt_in:
                    changes.append("opt_in->True")
                    contact.opt_in = True
                if not contact.name and name:
                    changes.append("name")
                    contact.name = name

                # profile_data é JSON puro (não MutableDict): COPIA-EDITA-REATRIBUI p/ marcar dirty.
                profile = dict(contact.profile_data or {})
                if profile.get("partner_customer_id") != partner_id:
                    profile["partner_customer_id"] = partner_id
                    changes.append("partner_customer_id")
                if profile.get("partner") != partner:
                    profile["partner"] = partner
                    changes.append(f"partner({partner['profile']})")
                if changes:
                    contact.profile_data = profile  # reatribui -> dirty no JSONB
                    updated += 1
                    print(f"  ~ atualizar {phone}: {', '.join(changes)}")
                else:
                    unchanged += 1

            # --- Mega Central: ingere os sinais do snapshot (NPS/churn) — SEM disparo.
            # classify=False: lote de 233 não vira 233 chamadas LLM (classificar depois).
            for spec in partner_feedback_specs(customer, classification):
                await ingest_feedback_item(session, org.id, contact.id, spec, classify=False)
                fb_items += 1

        await session.commit()  # único commit, fora do loop

    print(
        f"=== Sync executado: {created} criado(s), {updated} atualizado(s), "
        f"{unchanged} já em dia, {invalid} sem telefone, {skipped} ignorado(s); "
        f"{fb_items} sinal(is) na mega central ==="
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync de clientes Bizzu (Partner API) -> Escuta + classificacao por perfil."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="só imprime a distribuição por perfil (sem tocar o banco, sem PII)",
    )
    parser.add_argument(
        "--search",
        default="",
        help="filtro opcional repassado à API (?search=)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(sync(args.dry_run, args.search))


if __name__ == "__main__":
    raise SystemExit(main())
