import imaplib
import email
from email.header import decode_header
import os
import sys
import re
import unicodedata
from dotenv import load_dotenv

# Carrega credenciais do arquivo .env
load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
IMAP_SERVER = (os.getenv("IMAP_SERVER") or "imap.gmail.com").strip()

class ClassificadorEmailsRPA:
    def __init__(self):
        self.mail = None
        self.pasta_destino = '"Fechamento de caixa"' 

    def conectar(self):
        try:
            self.mail = imaplib.IMAP4_SSL(IMAP_SERVER)
            self.mail.login(EMAIL_USER, EMAIL_PASS)
            return True
        except Exception as e:
            print(f"❌ Falha na autenticação: {e}")
            return False

    def normalizar_texto(self, texto):
        if not texto: return ""
        # Remove acentuação e converte para maiúsculas para uniformizar a pesquisa
        texto_limpo = ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')
        return texto_limpo.upper().strip()

    def analisar_conteudo(self, assunto, corpo):
        # Consolida o assunto e o corpo num único bloco de texto normalizado
        texto_total = f"{self.normalizar_texto(assunto)} {self.normalizar_texto(corpo)}"
        
        # 🎯 GATILHOS DIRETOS: Se encontrar qualquer um destes termos isolados, valida imediatamente
        gatilhos_diretos = [
            "FECHAMENTO", "VALIDA PIX", "VALIDAPIX", "RESUMO PIX", 
            "RESUMO DO PIX", "VENDAS DO CAIXA", "DOUGLAS"
        ]
        
        if any(gatilho in texto_total for gatilho in gatilhos_diretos):
            return True
            
        # 🧠 COMBINAÇÕES LÓGICAS: Valida se encontrar palavras associadas no mesmo texto
        # Caso 1: Tem de ter a palavra RELATORIO combinada com outra palavra contextual
        if "RELATORIO" in texto_total and any(termo in texto_total for termo in ["DIARIO", "CAIXA", "VENDAS", "PIX", "ANEXO"]):
            return True
            
        # Caso 2: Tem de ter as palavras VENDAS e DIA no mesmo e-mail
        if "VENDAS" in texto_total and "DIA" in texto_total:
            return True
            
        return False

    def processar_caixa_entrada(self):
        self.mail.select("INBOX", readonly=False)
        status, mensagens = self.mail.search(None, "UNSEEN")
        
        if status != "OK" or not mensagens[0]:
            print("📭 Nenhum e-mail novo não lido encontrado.")
            return

        id_lista = mensagens[0].split()
        print(f"📥 {len(id_lista)} e-mails não lidos detetados. Iniciando triagem por palavras-chave...")

        for num_id in id_lista:
            status, dados = self.mail.fetch(num_id, "(RFC822)")
            if status != "OK": continue

            for resposta in dados:
                if isinstance(resposta, tuple):
                    msg = email.message_from_bytes(resposta[1])
                    
                    assunto, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(assunto, bytes):
                        assunto = assunto.decode(encoding or "utf-8", errors="ignore")
                    
                    corpo = ""
                    if msg.is_multipart():
                        for parte in msg.walk():
                            content_type = parte.get_content_type()
                            if content_type in ["text/plain", "text/html"]:
                                payload = parte.get_payload(decode=True).decode(errors="ignore")
                                if content_type == "text/html":
                                    payload = re.sub(r'<[^>]+>', ' ', payload)
                                corpo += f" {payload}"
                    else:
                        corpo = msg.get_payload(decode=True).decode(errors="ignore")
                        if msg.get_content_type() == "text/html":
                            corpo = re.sub(r'<[^>]+>', ' ', corpo)

                    assunto = assunto or ""
                    corpo = corpo or ""

                    e_fechamento_valido = self.analisar_conteudo(assunto, corpo)

                    if e_fechamento_valido:
                        print(f"   ✅ [MOVIDO] {assunto} -> Pasta: Fechamento de caixa")
                        resultado_copia = self.mail.copy(num_id, self.pasta_destino)
                        if resultado_copia[0] == b"OK" or resultado_copia[0] == "OK":
                            self.mail.store(num_id, "+FLAGS", "\\Deleted")
                    else:
                        print(f"   ⚠️ [IGNORADO] {assunto} -> Não corresponde aos critérios de fecho. Mantido na Inbox.")
                        self.mail.store(num_id, "-FLAGS", "\\Seen")
        
        self.mail.expunge()
        self.mail.logout()

if __name__ == "__main__":
    if not EMAIL_USER or not EMAIL_PASS:
        print("❌ Defina EMAIL_USER e EMAIL_PASS no arquivo .env")
        sys.exit()
        
    rpa = ClassificadorEmailsRPA()
    if rpa.conectar():
        rpa.processar_caixa_entrada()