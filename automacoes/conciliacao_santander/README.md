# Conciliação Bancária Santander & F360

Robô de automação desenvolvido em **Python + Selenium** para conciliação bancária entre contas corporativas e a plataforma financeira **F360**.

## 📌 Funcionalidades
- Autenticação e navegação segura em ambiente web corporativo.
- Varredura de lançamentos bancários pendentes dos últimos meses.
- Vínculo automático de extratos bancários com contas de movimento.
- Tratamento de exceções e tolerância a lentidões de rede com esperas explícitas (`WebDriverWait`).
- Configuração modular de lojas e contas bancárias via arquivo de configuração (`tarefas_config.json`).
