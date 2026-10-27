# Triagem & Classificação Inteligente de E-mails via IMAP

Agente assíncrono em **Python** para monitoramento de caixas de entrada corporativas, análise contextual de e-mails de fechamento de caixa e organização automática por pastas.

## 📌 Funcionalidades
- Conexão segura via protocolo **IMAP com SSL**.
- Decodificação de cabeçalhos (`RFC822`) e corpos de mensagem em formato texto puro ou HTML com decodificação Unicode/ASCII normalizada.
- Motor de regras semânticas combinando gatilhos diretos (e.g., termos de fechamento e resumos PIX) e correlações lógicas entre palavras-chave no mesmo contexto.
- Movimentação atômica dos e-mails elegíveis para as pastas de auditoria e arquivamento, mantendo mensagens não relacionadas intocadas na caixa de entrada.
