# Disparador Corporativo de Boletos com Multi-Anexos

Agente em **Python** para emissão e disparo em massa de faturas e boletos por e-mail com múltiplos anexos, integrado com a API do **Google Sheets** e envio via **SMTP**.

## 📌 Funcionalidades
- Leitura remota da esteira de cobrança em planilhas na nuvem com autenticação segura de Service Account.
- Motor com expressões regulares (Regex) para rastrear e vincular automaticamente boletos correspondentes a cada cliente/unidade.
- Suporte a múltiplos anexos em formato PDF na mesma mensagem (`MIMEMultipart`).
- Registro detalhado de logs de envio, taxa de sucesso e tratamento de erros de conexão SMTP.
