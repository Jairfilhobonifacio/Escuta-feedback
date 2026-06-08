# Análise Profunda — Infraestrutura Bizzu (gabarita-ai/infra)

> Leitura em 08/06/2026. Fonte: `~/Documents/Projetos/bizzu-repos/infra` (~56 arquivos).
> Arquivos lidos: `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`, `backend.tf`,
> `terraform.tfvars.example`, `environments/production/terraform.tfvars.example`,
> todos os `*-secrets.tf`, `secrets-policy.tf`, `modules/*/main.tf`, `modules/*/variables.tf`,
> `modules/radar-editais-ec2/user_data.sh`, `docs/INDEX.md` e docs individuais por módulo.

---

## Resumo Executivo

- **Cloud AWS us-east-1**, Terraform >= 1.0 com provider `hashicorp/aws ~> 5.0`. State remoto em S3 (`bizzu-terraform-state-633146206248/infra/terraform.tfstate`) com lock nativo (`use_lockfile`, requer Terraform >= 1.11).
- **11 módulos Terraform**: networking (VPC), dns-cert (Route 53 + ACM wildcard `*.bizzu.ai`), rds, elasticache, api-alb, api-asg, api-ec2, worker-asg, s3-cloudfront, s3-bucket, radar-editais-ec2. Ambiente único (`production`); sem workspaces ou diretórios `dev/staging`.
- **Compute**: ALB público + ASG NestJS (min 2 / max 4, `t4g.small` ARM64) + ASG Worker BullMQ (min 1 / max 3, `t4g.medium`) + EC2 individual para o site Next.js (`api-ec2`) + EC2 individual para o Radar Editais FastAPI (`radar-editais-ec2`). Todos em Amazon Linux 2023.
- **Dados**: RDS PostgreSQL 15 (`db.t3.small` Multi-AZ, gp3 criptografado, backup 7 dias, subnets privadas) + ElastiCache Redis 7.1 (`cache.t4g.micro`, subnets privadas). O Radar compartilha o mesmo RDS via `DATABASE_URL` (SG rule aberta).
- **Segredos**: 16 arquivos `*-secrets.tf` criam segredos em AWS Secrets Manager no namespace `prod/plataforma/*` (+ `prod/site/database` + `prod/radar-editais/db`). Instâncias consomem via IAM role; nenhum segredo versionado.
- **ACM wildcard `*.bizzu.ai` já emitido** (us-east-1). Qualquer subdomínio novo — incluindo `escuta.bizzu.ai` — é coberto sem nova solicitação de certificado.
- **Caminho recomendado para hospedar o Escuta**: criar `modules/escuta-ec2/` clonando o padrão de `radar-editais-ec2` (EC2 + EIP + Caddy + Route 53 A record), adicionar `escuta-secrets.tf` com path `prod/escuta/*`, referenciar subnet pública existente e zona Route 53 já provisionada. O Supabase do Escuta permanece separado do RDS Bizzu.

---

## 1. Visão Geral

| Item | Valor |
|---|---|
| Cloud | AWS |
| Região principal | `us-east-1` (us-east-1 também para ACM CloudFront, via provider alias) |
| Ferramenta | Terraform >= 1.0; provider AWS ~> 5.0 |
| State | S3 remoto: bucket `bizzu-terraform-state-633146206248`, key `infra/terraform.tfstate`, criptografado, lock nativo `use_lockfile` (Terraform >= 1.11) |
| Ambientes | Apenas `production` (`environments/production/terraform.tfvars.example`); sem separação dev/staging |
| Organização | Módulo por componente em `modules/`; secrets em arquivos raiz `*-secrets.tf`; política IAM consolidada em `secrets-policy.tf` |

O estado remoto ficou ativo em maio/2026 (commit `afa1c83`). O `terraform.tfstate.zip` antigo que continha a senha do RDS foi removido do tracking; senha deve estar rotacionada.

---

## 2. Recursos Provisionados

### 2.1 Compute (EC2 / ASG)

**API NestJS — ALB + ASG** (`modules/api-alb` + `modules/api-asg`):
- ALB público (`bizzu-api-alb`), listeners 80→301 e 443 (TLS 1.3, ACM), target group na porta 3000, health check em `/health`.
- ASG: min 2 / max 4 instâncias, `t4g.small` ARM64 (Amazon Linux 2023), 30 GB gp3. Rolling instance refresh. CloudWatch alarms (CPU > 70% → scale up; CPU < 20% → scale down).
- `user_data.sh`: instala Node 22, baixa artefato do S3 artifact bucket, injeta segredos do Secrets Manager, escreve `.env` (chmod 600), sobe serviço systemd `bizzu-api`.
- DNS: `api.bizzu.ai` → CNAME para `module.api_alb.alb_dns_name` (apontado no Cloudflare — comentário no `main.tf` linha 114).

**Site Next.js — EC2 individual** (`modules/api-ec2`):
- Instância `t4g.small` (ARM64), EIP estático, Caddy (Let's Encrypt), app em `/opt/bizzu-site`, 20 GB gp3.
- DNS: Route 53 A records para `bizzu.ai` e `www.bizzu.ai` → EIP.
- IAM role lê segredos: `prod/plataforma/database`, `prod/site/database`, `prod/plataforma/datadog`.

**Worker BullMQ — ASG** (`modules/worker-asg`):
- min 1 / max 3 instâncias, `t4g.medium` ARM64, 30 GB gp3. Sem ALB. CloudWatch alarms duplos: CPU e métrica customizada `Bizzu/Worker:QueueDepth` (> 5 → scale up; < 1 por 5 min → scale down).
- Processa filas BullMQ via Redis (seletor, geração de plano, extração de edital, comentário IA etc.).

**Radar Editais — EC2 individual** (`modules/radar-editais-ec2`):
- Instância `t4g.small` (ARM64, padrão; configurável via `radar_editais_instance_type`), EIP, Caddy, app FastAPI (uvicorn) em `/opt/radar-editais`, porta 7400.
- Systemd: `radar-editais.service` (uvicorn) + `radar-editais-sync.timer` (cron diário às 07:00 UTC).
- DNS: Route 53 A record `radar-editais.bizzu.ai` → EIP.
- IAM: lê `prod/plataforma/llm`, `prod/plataforma/jwt`, `prod/radar-editais/db`; acesso S3 ao bucket de PDFs.

### 2.2 Banco de Dados — RDS PostgreSQL

- Módulo: `modules/rds`. Identificador: `bizzu-postgres`.
- Engine: PostgreSQL 15, `db.t3.small` (variável `rds_instance_class`, default `db.t3.small`; tfvars.example usa `t3.micro` Free Tier).
- `multi_az = true` (produção); armazenamento 20 GB gp3 (auto-grow até 100 GB), criptografado.
- `backup_retention_period = 7`, `deletion_protection = true`.
- Subnets privadas (padrão). Acesso externo opt-in via `rds_publicly_accessible + rds_allowed_cidr_blocks`.
- SG rules em `main.tf` abrem porta 5432 para: `module.api_asg.security_group_id`, `module.worker_asg.security_group_id`, `module.radar_editais_ec2.security_group_id`.
- Banco padrão: `bizzudb` (variável `db_name`, default `bizzudb`; tfvars diz `plataforma`).
- Credenciais: secret `prod/plataforma/database` (campos: `username`, `password`, `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`).

### 2.3 Cache — ElastiCache Redis

- Módulo: `modules/elasticache`.
- Engine: Redis 7.1, `cache.t4g.micro`, 1 nó, porta 6379, subnets privadas.
- `maxmemory-policy = noeviction` (jobs BullMQ nunca eviccionados).
- SG rules: porta 6379 liberada somente para os SGs da API-ASG e Worker-ASG.
- Secret: `prod/plataforma/redis`.

### 2.4 Rede — VPC

- Módulo: `modules/networking`. CIDR `10.0.0.0/16`, 2 AZs.
- 2 subnets públicas (`/20` aprox.): ALB, EC2 com EIP. Internet Gateway.
- 2 subnets privadas: RDS, ElastiCache. Sem NAT Gateway (economia de custo: instâncias privadas sem saída direta para internet).
- Route tables: públicas ligadas ao IGW; privadas sem rota default.

### 2.5 Storage — S3

| Bucket (nome padrão) | Módulo | Uso |
|---|---|---|
| `bizzu-landing-lp-bizzu-ai` (gerado) | `s3-cloudfront` | Landing pages (lp.bizzu.ai) |
| `bizzu-plataforma-plataforma-bizzu-ai` (gerado) | `s3-cloudfront` | Frontend Vite (plataforma.bizzu.ai) |
| `plataforma-images-prod` | `s3-bucket` | Imagens privadas do backend (ETL migrations) |
| `bizzu-deploy-artifacts` | `s3-bucket` | Artefatos de deploy (CI → ASG instance refresh) |
| `radar-editais-pdfs` | `s3-bucket` | PDFs do Radar Editais |

Todos privados (`block_public_acls = true`). Buckets CloudFront usam OAC (Origin Access Control, não OAI legado).

### 2.6 CDN — CloudFront

- Módulo: `modules/s3-cloudfront`. Duas distribuições: landing (`spa_fallback = false`) e plataforma (`spa_fallback = true`, erros 403/404 → `index.html`).
- `PriceClass_100` (US + Europa), IPv6 habilitado, TLS mínimo 1.2, compressão ativa, TTL padrão 1h.
- Certificado ACM de `us-east-1` (obrigatório para CloudFront).

### 2.7 DNS — Route 53

- Módulo: `modules/dns-cert`. Hosted zone `bizzu.ai` criada pelo Terraform (`create_zone = true`).
- Records gerenciados: A records para `bizzu.ai`, `www.bizzu.ai`, `radar-editais.bizzu.ai` (→ EIPs); Alias records para `plataforma.bizzu.ai`, `lp.bizzu.ai` (→ CloudFront); registro CNAME para `api.bizzu.ai` feito fora do Terraform (no Cloudflare, conforme comentário `main.tf:114`).
- **Sem SQS** no código atual.
- **Sem Secrets Manager via SSM** — uso direto do Secrets Manager.
- **Sem WAF/Shield** explícito no código.

---

## 3. Módulos — Descrição

| Módulo | Localização | O que cria |
|---|---|---|
| `networking` | `modules/networking/` | VPC, 2 subnets públicas + 2 privadas, IGW, route tables/associations |
| `dns-cert` | `modules/dns-cert/` | Route 53 hosted zone (opcional), ACM cert (`bizzu.ai` + `*.bizzu.ai`, DNS validation), records de validação |
| `s3-cloudfront` | `modules/s3-cloudfront/` | S3 bucket privado, OAC, CloudFront distribution, Route 53 alias records; suporte a SPA fallback |
| `s3-bucket` | `modules/s3-bucket/` | S3 bucket privado simples (sem CloudFront); usado para images, artifacts, PDFs |
| `rds` | `modules/rds/` | RDS PostgreSQL, subnet group, security group |
| `elasticache` | `modules/elasticache/` | ElastiCache cluster Redis, subnet group, parameter group, security group + SG rules |
| `api-alb` | `modules/api-alb/` | ALB, listeners HTTP/HTTPS, target group (porta 3000), SG |
| `api-asg` | `modules/api-asg/` | Launch template, ASG, IAM role/profile/policy, SG, CloudWatch alarms + scaling policies |
| `api-ec2` | `modules/api-ec2/` | EC2 individual (site), EIP, IAM role (acesso a secrets), SG, Route 53 A records (raiz + www) |
| `worker-asg` | `modules/worker-asg/` | Launch template, ASG (sem ALB), IAM role, SG, CloudWatch alarms (CPU + queue depth) |
| `radar-editais-ec2` | `modules/radar-editais-ec2/` | EC2, EIP, IAM role (llm/jwt/db secrets + S3 PDFs), SG, Route 53 A record; user_data instala Python 3.11 + uvicorn + Caddy; systemd para uvicorn + timer diário |

---

## 4. Ambientes

Existe apenas **um ambiente**: `production`. O diretório `environments/production/` contém só um `terraform.tfvars.example`. Não há `dev`, `staging` ou workspaces Terraform.

Consequência para o Escuta: não há ambiente de homologação Bizzu para testar antes de produção. Qualquer módulo novo entra direto em `production`.

---

## 5. Segredos e Configuração

### Namespacing no Secrets Manager

| Path | Arquivo `*-secrets.tf` | Campos relevantes |
|---|---|---|
| `prod/plataforma/database` | `database-secrets.tf` | `username`, `password`, `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` |
| `prod/site/database` | `site-database-secrets.tf` | idem, para o site Next.js |
| `prod/plataforma/jwt` | `jwt-secrets.tf` | `JWT_SECRET` |
| `prod/plataforma/encryption` | `encryption-secrets.tf` | chave(s) de criptografia (CPF etc.) |
| `prod/plataforma/redis` | `redis-secrets.tf` | endpoint Redis |
| `prod/plataforma/llm` | `llm-secrets.tf` | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` |
| `prod/plataforma/stripe` | `stripe-secrets.tf` | chaves Stripe |
| `prod/plataforma/asaas` | `asaas-secrets.tf` | chaves Asaas |
| `prod/plataforma/mercadolivre` | `mercadopago-secrets.tf` | chaves Mercado Pago |
| `prod/plataforma/sendgrid` | `sendgrid-secrets.tf` | `SENDGRID_API_KEY` |
| `prod/plataforma/sendkit` | `sendkit-secrets.tf` | chave SendKit |
| `prod/plataforma/google-oauth` | `google-oauth-secrets.tf` | OAuth Google |
| `prod/plataforma/facebook-oauth` | `facebook-oauth-secrets.tf` | OAuth Facebook |
| `prod/plataforma/google-sheet` | `google-sheet-secrets.tf` | service account Google Sheets |
| `prod/plataforma/datadog` | `datadog-secrets.tf` | `DATADOG_API_KEY` |
| `prod/radar-editais/db` | `radar-editais-secrets.tf` | `DATABASE_HOST/PORT/NAME/USER/PASSWORD` |

### Fluxo de consumo

`terraform apply` cria os secrets com valores vazios → operador popula via `aws secretsmanager put-secret-value` (comentários em cada `*-secrets.tf` mostram o comando exato) → `user_data.sh` das instâncias lê via `aws secretsmanager get-secret-value` no boot e escreve `.env` (modo 600) → serviço systemd carrega `EnvironmentFile`.

IAM policy consolidada em `secrets-policy.tf`: permite `GetSecretValue` em `prod/plataforma/*` e `prod/site/*` para os roles da API-ASG e Worker-ASG. O Radar-Editais tem policy própria mais restrita (só `llm`, `jwt`, `db` do radar).

### Variável crítica de apply

`TF_VAR_db_password` — obrigatório no ambiente onde `terraform apply` é executado. Sem ela o apply falha.

---

## 6. Domínios, DNS e Certificados

| Domínio | Tipo DNS | Destino | Certificado |
|---|---|---|---|
| `bizzu.ai` | Route 53 A → EIP | EC2 site (`api-ec2`) | Caddy / Let's Encrypt (na instância) |
| `www.bizzu.ai` | Route 53 A → EIP | EC2 site | idem |
| `api.bizzu.ai` | CNAME (Cloudflare, fora do TF) | ALB (`module.api_alb.alb_dns_name`) | ACM wildcard (ALB listener) |
| `plataforma.bizzu.ai` | Route 53 Alias → CloudFront | S3+CloudFront | ACM wildcard (us-east-1) |
| `lp.bizzu.ai` | Route 53 Alias → CloudFront | S3+CloudFront | ACM wildcard (us-east-1) |
| `radar-editais.bizzu.ai` | Route 53 A → EIP | EC2 radar | Caddy / Let's Encrypt |
| `suporte.bizzu.ai` | MX / SendGrid Inbound Parse | SendGrid | — (email, não HTTP) |

**ACM**: certificado único `bizzu.ai` + SAN `*.bizzu.ai`, emitido em `us-east-1`, validação DNS via Route 53. Cobre qualquer subdomínio de primeiro nível (ex.: `escuta.bizzu.ai`, `escuta2.bizzu.ai`) sem nova solicitação.

**Observação sobre `api.bizzu.ai`**: o comentário no `main.tf` linha 114 instrui definir um CNAME no Cloudflare. Isso significa que a zona primária do `api` está no Cloudflare, não no Route 53 — potencial duplo salto DNS. Os demais subdomínios usam Route 53 direto.

---

## 7. Onde o Escuta Vai Morar — Análise e Caminho Concreto

### Contexto do Escuta

O Escuta é composto por:
- **FastAPI** (Python) — backend NPS/pesquisa, porta 8000
- **WAHA** (WhatsApp HTTP API) — container Docker, porta 3000 ou 3001
- **Supabase** — banco de dados do Escuta (projeto `nlqeargxkidygbrahkbk`, conta `boxtrust34`, separado do RDS Bizzu)

### O RDS Bizzu é compartilhável?

**Não recomendado para o Escuta.** O RDS usa PostgreSQL 15 com Multi-AZ, mas pertence ao schema da plataforma Bizzu (banco `bizzudb`/`plataforma`). Adicionar o Escuta ao mesmo RDS criaria: (a) acoplamento de dados entre produtos distintos; (b) necessidade de criar usuário/schema separado no RDS Bizzu; (c) dependência operacional. O Escuta já tem Supabase próprio (`escuta` em `sa-east-1`) — mantê-lo separado é o caminho correto.

### Padrão disponível: `radar-editais-ec2`

O módulo `modules/radar-editais-ec2/` é o template ideal. Ele já resolve exatamente o caso de uso do Escuta:
- EC2 individual com EIP + Caddy (TLS automático via Let's Encrypt)
- IAM role com acesso restrito a seus próprios secrets
- Route 53 A record para `<subdomain>.bizzu.ai`
- `user_data.sh` que instala runtime, lê secrets do Secrets Manager, escreve `.env`, configura systemd

### Caminho concreto

**Passo 1 — Módulo Terraform `modules/escuta-ec2/`**

Criar clonando `modules/radar-editais-ec2/` com as seguintes adaptações:

- `app_dir = "/opt/escuta"`
- `subdomain = "escuta"`
- `user_data.sh`: instala Python 3.11 + Docker (para WAHA) + uvicorn; puxa secrets de `prod/escuta/*`
- Systemd: `escuta-fastapi.service` (uvicorn porta 8000) + `waha.service` (Docker porta 3001, interno)
- Caddyfile: `escuta.bizzu.ai → localhost:8000` (FastAPI); WAHA não exposto diretamente

**Passo 2 — `escuta-secrets.tf` (novo arquivo raiz)**

```hcl
resource "aws_secretsmanager_secret" "escuta" {
  name        = "prod/escuta/app"
  description = "Credenciais do Escuta (Supabase, WAHA, Webhook)."
}
```

Campos: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `WAHA_API_KEY`, `HOOK_SECRET`, `ADMIN_API_KEY`.

**Passo 3 — Referência em `main.tf`**

```hcl
module "escuta_ec2" {
  source          = "./modules/escuta-ec2"
  name_prefix     = var.project_name
  domain          = var.domain
  instance_type   = "t4g.small"         # ARM64, ~$0.017/h
  vpc_id          = module.networking.vpc_id
  subnet_id       = module.networking.public_subnet_ids[0]
  route53_zone_id = module.dns_cert.route53_zone_id
  aws_region      = var.aws_region
  ssh_key_name    = var.ssh_key_name != "" ? var.ssh_key_name : null
  secret_name     = "prod/escuta/app"
}
```

**Passo 4 — Security Group do Escuta**

O módulo cria seu próprio SG:
- Ingress 22 (SSH opcional, CIDR restrito)
- Ingress 80 + 443 (Caddy)
- Egress 0.0.0.0/0

WAHA (porta 3001) **não** precisa de ingress externo — FastAPI chama localmente. Se o Escuta precisar receber webhooks do WAHA externamente, abrir 3001 restrito ao próprio IP da instância (loopback basta).

**Passo 5 — DNS**

Route 53 A record `escuta.bizzu.ai` → EIP da instância. Gerenciado dentro do módulo (idêntico ao radar). ACM wildcard já cobre sem alteração.

**Passo 6 — Deploy**

Seguir o mesmo padrão do radar: SSH na instância + `git pull` + `systemctl restart escuta-fastapi`. Para deploy sem SSH: script `scripts/deploy/escuta` similar ao `landing`, ou considerar instance refresh de um ASG de 1 instância (over-engineering para o tamanho atual).

### WAHA — Considerações

O WAHA precisa de:
- Docker instalado na instância (não presente no `user_data.sh` do radar; adicionar `dnf install -y docker` + `systemctl enable --now docker`)
- Volume persistente para sessão WhatsApp (`/opt/escuta/waha-data`)
- Não expor porta 3001 externamente (comunicação interna apenas)
- Secret para `WAHA_API_KEY` em `prod/escuta/app`

### Alternativa: EC2 separado para WAHA

Se WAHA precisar de mais recursos (sessões múltiplas, alto volume), criar uma segunda instância `modules/waha-ec2/` menor (`t4g.micro`) na mesma VPC, com comunicação interna via IP privado. Para o piloto Bizzu (1 número, baixo volume), colocar tudo na mesma instância é suficiente.

### Separação Supabase x RDS

| | Escuta | Bizzu |
|---|---|---|
| Banco | Supabase `nlqeargxkidygbrahkbk` (sa-east-1, conta `boxtrust34`) | RDS `bizzu-postgres` (us-east-1) |
| Acesso | Via secret `prod/escuta/app` | Via secret `prod/plataforma/database` |
| SG rule no RDS | **Nenhuma** (Escuta não toca o RDS) | API + worker + radar |

Manter separado elimina qualquer risco de schema collision e simplifica o offboarding caso o Escuta seja descontinuado.

---

## 8. Resumo Executivo Detalhado

1. **Infraestrutura madura, custo-otimizada**: ALB+ASG para a API (HA real), EC2 individuais para serviços menores (site, radar), Redis gerenciado, RDS Multi-AZ. Sem ECS/Lambda/Fargate — tudo EC2. Tudo ARM64 (`t4g.*`) onde possível.

2. **11 módulos bem estruturados**: cada um com `main.tf`, `variables.tf`, `outputs.tf`. O módulo `radar-editais-ec2` é o template direto para o Escuta (FastAPI + Caddy + systemd).

3. **Secrets Manager bem organizado** (`prod/plataforma/*`): 16 segredos, cada um em arquivo dedicado `*-secrets.tf`. Adicionar `prod/escuta/*` segue o padrão sem atrito.

4. **ACM wildcard `*.bizzu.ai` já ativo** (us-east-1): `escuta.bizzu.ai` é coberto sem nenhuma mudança no módulo `dns-cert`.

5. **Ambiente único (`production`)**: não há staging/dev IaC. Testar mudanças de infra exige cuidado — qualquer `terraform apply` vai direto para produção.

6. **Ponto de atenção**: `api.bizzu.ai` usa CNAME no Cloudflare (fora do Terraform), não Route 53. Os demais subdomínios são Route 53. O `escuta.bizzu.ai` seguirá o padrão Route 53 (como o radar).

7. **Custo estimado do Escuta**: `t4g.small` (~$0.017/h) ≈ $12/mês + EIP ($0.005/h ocioso = $3.6/mês se parado, $0 se sempre rodando) + R53 query charges irrisórios. Total: ~$12-16/mês.

---

## Caminhos-Chave

| Arquivo | Relevância |
|---|---|
| `infra/main.tf` | Orquestração de todos os módulos; adicionar `module "escuta_ec2"` aqui |
| `infra/variables.tf` | Adicionar `escuta_secret_name`, `escuta_instance_type` |
| `infra/modules/radar-editais-ec2/` | Template para `modules/escuta-ec2/` |
| `infra/modules/radar-editais-ec2/user_data.sh` | Base para o `user_data.sh` do Escuta (Python + Caddy + systemd) |
| `infra/radar-editais-secrets.tf` | Base para `escuta-secrets.tf` |
| `infra/secrets-policy.tf` | Adicionar attachment do IAM role do Escuta se necessário |
| `infra/backend.tf` | State remoto S3; não alterar |
| `infra/modules/dns-cert/main.tf` | Confirma wildcard `*.bizzu.ai` — sem necessidade de alteração |
| `infra/docs/secrets.md` | Documentação canônica dos secrets |
| `infra/docs/radar-editais.md` | Descrição do módulo usado como template |
