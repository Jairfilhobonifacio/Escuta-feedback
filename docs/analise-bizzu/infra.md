# Relatório do agente — Infra Bizzu (gabarita-ai/infra)

> Exploração automática em 07/06/2026. Clone local: `~/Documents/Projetos/bizzu-repos/infra`.

## 1. Cloud — AWS us-east-1

- **Compute:** ALB (TLS) → ASG API NestJS (min 2/max 4, t4g.small/medium ARM64) + ASG Worker BullMQ (min 1/max 3) + EC2 individuais (Site Next.js, Radar FastAPI)
- **Banco:** RDS PostgreSQL db.t3.small Multi-AZ, banco `plataforma` (Sequelize), backup 7d, gp3 criptografado, subnets privadas
- **Cache/Fila:** ElastiCache Redis cache.t4g.micro (BullMQ), porta 6379 privada
- **Storage:** S3 (`site`, `landing`, `plataforma`, `plataforma-images`, `artifact`, `radar-editais-pdfs`) + CloudFront (OAC)
- **DNS/TLS:** Route 53 (`bizzu.ai`) + ACM wildcard `*.bizzu.ai`

## 2. IaC — Terraform (~5.0)

State remoto: S3 `bizzu-terraform-state-633146206248/infra/terraform.tfstate` (lockfile nativo ≥1.11).

```
modules/
├── networking/        # VPC 10.0.0.0/16, 2 AZs, 2 public + 2 private
├── dns-cert/          # Route53 + ACM
├── rds/  ├── elasticache/  ├── api-alb/  ├── api-asg/  ├── api-ec2/ (site, legacy)
├── worker-asg/  ├── s3-cloudfront/  ├── s3-bucket/  └── radar-editais-ec2/
```

Variáveis críticas: `aws_region=us-east-1`, `domain=bizzu.ai`, `environment=production`, `db_password` via `TF_VAR_db_password` (env), `rds_publicly_accessible=false`.

## 3. CI/CD

**Sem GitHub Actions** — deploy manual via scripts (`scripts/deploy/`):
- Landing/frontend: `aws s3 sync` + invalidação CloudFront
- API/Worker: build NestJS → artefato S3 → `aws autoscaling start-instance-refresh`
- Provisioning: `user_data.sh` baixa artefato + injeta secrets do Secrets Manager → `.env` (600) → NestJS (Node 22, Amazon Linux 2023)
- Migrations: `npm run db:migrate` (sequelize-cli), manual

## 4. Domínios

| Domínio | Origem |
|---|---|
| bizzu.ai / www | EC2 site (EIP, Caddy/Let's Encrypt) |
| api.bizzu.ai | ALB (CNAME via Cloudflare) |
| plataforma.bizzu.ai | S3+CloudFront (frontend Vite) |
| lp.bizzu.ai | S3+CloudFront |
| radar-editais.bizzu.ai | EC2 radar |
| suporte.bizzu.ai | SendGrid inbound parse (MX) — respostas de email |

Segurança: ALB SG 80→301/443; API SG 3000 (só ALB); RDS SG 5432 (só API/worker/radar); Redis 6379 (só API/worker).

## 5. Secrets — AWS Secrets Manager (`prod/plataforma/*`)

database, asaas, stripe, encryption, google-oauth, facebook-oauth, google-sheet, sendgrid, sendkit, jwt, llm, datadog, mercadolivre, redis + `prod/site/database` + `prod/radar-editais/db`.
Injeção: `user_data.sh` → `aws secretsmanager get-secret-value` → `.env`. IAM role das instâncias permite `GetSecretValue` em `prod/plataforma/*`.

## 6. Webhooks existentes (backend)

`POST /webhooks/payments|mercadopago|asaas` → `WebhookService.handleWebhook(provider, payload, headers)` → valida assinatura → normaliza → persiste `WebhookEvent` → efeitos (subscription/payment).

## 7. Como o Escuta se conecta

### (a) Bizzu → Escuta (eventos)
Criar módulo `src/escuta/` no NestJS (controller/service), secret `prod/plataforma/escuta`, POST assinado para o endpoint do Escuta. Alternativa: EventEmitter2 + Redis pub/sub (mais acoplamento de infra).

### (b) Hospedagem do Escuta (mesma cloud)
Módulo Terraform `modules/escuta-ec2/`: EC2 t4g.small ARM na VPC existente, `escuta.bizzu.ai` (wildcard ACM já cobre), SG próprio (8000 interno), secrets `prod/escuta/*`, WAHA como container na mesma instância, artefatos em S3. RDS deles ≠ Supabase do Escuta (mantém separado).

```hcl
module "escuta_ec2" {
  source            = "./modules/escuta-ec2"
  vpc_id            = module.networking.vpc_id
  subnet_id         = module.networking.public_subnet_ids[0]
  route53_zone_id   = module.dns_cert.route53_zone_id
  root_domain       = var.domain
  instance_type     = "t4g.small"
  supabase_secret_name = "prod/escuta/supabase"
}
```

## Caminhos-chave

`infra/modules/` · `infra/*-secrets.tf` · `scripts/deploy/` · `backend/src/payments/webhook.controller.ts` · `DEPLOY.md` (canônico) · `infra/docs/flows/deploy.md`
