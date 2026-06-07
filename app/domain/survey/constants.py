"""Constantes do domínio de Survey (stdlib-only, sem dependências pesadas).

Fica isolado para que a lógica pura (logic.py) seja importável/testável sem
SQLAlchemy. Os models (survey.py) reexportam daqui.
"""

# Estados de survey_responses
STATUS_SENT = "sent"                          # pergunta enviada, aguardando o NPS
STATUS_AWAITING_REASON = "awaiting_reason"    # NPS recebido, aguardando o "por quê"
STATUS_CLOSED = "closed"                      # encerrada
STATUS_EXPIRED = "expired"                    # passou da janela sem resposta
