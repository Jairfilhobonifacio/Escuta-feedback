"""Monitor temporario: transcript ao vivo de um contato, reusando a conexao do app
(app.db.SessionLocal — mesma que o backend usa, sem o problema de TLS do pooler).
Uso: python scripts/_watch.py [phone] [duracao_seg]. Apagar depois."""
import asyncio, os, sys, time
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for line in (Path(_ROOT) / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import truststore
truststore.inject_into_ssl()
from sqlalchemy import select
from app.db import SessionLocal
from app.models.core import Contact
from app.models.survey import Message, SurveyResponse

PHONE = sys.argv[1] if len(sys.argv) > 1 else "5524998365809"
DUR = int(sys.argv[2]) if len(sys.argv) > 2 else 120


async def main():
    seen, last, closed = set(), None, False
    deadline = time.time() + DUR
    print(f"[monitor] phone={PHONE} janela={DUR}s", flush=True)
    while time.time() < deadline:
        async with SessionLocal() as s:
            cid = (await s.execute(select(Contact.id).where(Contact.phone == PHONE).limit(1))).scalar()
            if cid:
                msgs = (await s.execute(
                    select(Message).where(Message.contact_id == cid).order_by(Message.created_at)
                )).scalars().all()
                for m in msgs:
                    key = (m.created_at.isoformat(), m.direction, m.body)
                    if key in seen:
                        continue
                    seen.add(key)
                    who = "VOCE" if str(m.direction).lower().startswith("in") else "BOT "
                    print(f"  [{m.created_at.strftime('%H:%M:%S')}] {who}: {m.body}", flush=True)
                r = (await s.execute(
                    select(SurveyResponse).where(SurveyResponse.contact_id == cid)
                    .order_by(SurveyResponse.sent_at.desc()).limit(1)
                )).scalar_one_or_none()
                if r and r.status != last:
                    last = r.status
                    print(f"  -- status: {r.status} score={r.answer_score} bucket={r.nps_bucket}", flush=True)
                if r and r.status == "closed":
                    closed = True
                    print(">> CONVERSA FECHADA", flush=True)
                    break
        await asyncio.sleep(4)
    if not closed:
        print(">> fim da janela (sem fechamento)", flush=True)


asyncio.run(main())
