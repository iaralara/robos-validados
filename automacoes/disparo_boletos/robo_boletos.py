import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import gspread
import os
import time
import re
from dotenv import load_dotenv

# Destranca o cofre de variáveis de ambiente
load_dotenv()

print("🤖 Iniciando o Agente de Disparo de Boletos (Versão de Produção c/ Múltiplos Anexos)...")

# =========================================================
# 1. CREDENCIAIS DO GMAIL (Remetente)
# =========================================================
EMAIL_REMETENTE = os.getenv("MEU_EMAIL")
SENHA_APP = os.getenv("MINHA_SENHA") # ⚠️ Cole as 16 letras geradas no Google
SERVIDOR_SMTP = "smtp.gmail.com"
PORTA_SMTP = 587

# =========================================================
# 2. INTELIGÊNCIA DE DIRETÓRIOS E CHAVE
# =========================================================
if getattr(sys, 'frozen', False):
    diretorio_atual = os.path.dirname(sys.executable) 
else:
    diretorio_atual = os.path.dirname(os.path.abspath(__file__)) 

caminho_chave = os.path.join(diretorio_atual, "chave_google.json")
pasta_boletos = os.path.join(diretorio_atual, "Boletos")

# =========================================================
# 3. CONEXÃO COM O GOOGLE SHEETS
# =========================================================
print(f"🔍 Chave validada no endereço: {caminho_chave}")

try:
    if not os.path.exists(caminho_chave):
        raise FileNotFoundError("O arquivo 'chave_google.json' não está na pasta.")
        
    cliente = gspread.service_account(filename=caminho_chave)
    planilha = cliente.open_by_key(os.getenv("SPREADSHEET_ID_BOLETOS", "SUA_PLANILHA_ID_AQUI")) 
    aba = planilha.worksheet("Robo boletos") 
    registros = aba.get_all_records() 
    print("✅ Planilha 'Robo boletos' carregada com sucesso!")
    
except Exception as e:
    print(f"❌ ERRO CRÍTICO na Planilha: {type(e).__name__} - {e}")
    input("\nPressione ENTER para fechar...")
    sys.exit()

# =========================================================
# 4. MOTOR DE DISPARO DE E-MAILS (COM MULTI-ANEXOS REGEX)
# =========================================================
try:
    print("\n🔑 Autenticando no servidor do Gmail...")
    servidor = smtplib.SMTP(SERVIDOR_SMTP, PORTA_SMTP)
    servidor.starttls() 
    servidor.login(EMAIL_REMETENTE, SENHA_APP)
    print("✅ Conexão com Gmail estabelecida!\n")
    
    sucessos = 0
    falhas = 0

    for linha in registros:
        nome_cliente = str(linha.get('GERENTE', '')).strip()
        nome_loja = str(linha.get('NOME FANTASIA', '')).strip()
        email_cliente = str(linha.get('EMAIL', '')).strip()
        nome_base_pdf = str(linha.get('ARQUIVO_PDF', '')).strip() 
        
        # Ignora linhas vazias
        if not email_cliente or email_cliente.upper() == "EMAIL":
            continue

        if not nome_base_pdf:
            print(f"⚠️ PULADO: A unidade {nome_loja} não tem arquivo PDF na planilha.")
            continue

        # Limpa o ".pdf" se o usuário tiver digitado na planilha, para padronizar a busca
        nome_base_pdf = re.sub(r'\.pdf$', '', nome_base_pdf, flags=re.IGNORECASE)

        # 🧠 VARREDURA REGEX: Encontra o arquivo original e todas as cópias (1), (2), etc.
        arquivos_encontrados = []
        if os.path.exists(pasta_boletos):
            # O Regex aceita "Nome.pdf" ou "Nome (1).pdf", "Nome (2).pdf", etc.
            padrao_regex = re.compile(rf"^{re.escape(nome_base_pdf)}( \(\d+\))?\.pdf$", re.IGNORECASE)
            
            for arquivo_na_pasta in os.listdir(pasta_boletos):
                if padrao_regex.match(arquivo_na_pasta):
                    arquivos_encontrados.append(arquivo_na_pasta)

        if not arquivos_encontrados:
            print(f"⚠️ PULADO: Nenhum boleto encontrado para a base '{nome_base_pdf}' ({nome_loja}).")
            falhas += 1
            continue

        # Montagem do E-mail
        mensagem = MIMEMultipart()
        mensagem['From'] = EMAIL_REMETENTE
        mensagem['To'] = email_cliente.replace(';', ',')
        mensagem['Subject'] = f"Boleto {nome_loja}"
        
        corpo_email = (
            f"Bom dia!\n\n"
            f"Seguem os boletos para pagamento. \n\n"
            "Atenciosamente,\n"
            "Iara Lara"
        )
        mensagem.attach(MIMEText(corpo_email, 'plain'))

        # Acopla todos os PDFs encontrados no mesmo e-mail
        for arquivo in arquivos_encontrados:
            caminho_pdf_completo = os.path.join(pasta_boletos, arquivo)
            with open(caminho_pdf_completo, "rb") as arquivo_anexo:
                parte_anexo = MIMEApplication(arquivo_anexo.read(), _subtype="pdf")
                parte_anexo.add_header('Content-Disposition', 'attachment', filename=arquivo)
                mensagem.attach(parte_anexo)

        # Disparo
        try:
            servidor.send_message(mensagem)
            print(f"📧 ENVIADO: {nome_cliente} -> {mensagem['To']} ({len(arquivos_encontrados)} anexos)")
            sucessos += 1
            time.sleep(2) # Pausa para não estourar o limite de requisições do Gmail
        except Exception as e:
            print(f"❌ ERRO DE ENVIO para {nome_cliente}: {e}")
            falhas += 1

    servidor.quit()
    print(f"\n🎉 Automação Finalizada! Sucessos: {sucessos} | Falhas: {falhas}")

except Exception as e:
    print(f"❌ Falha crítica no SMTP (E-mail): {e}")

input("\nPressione ENTER para fechar o robô...")