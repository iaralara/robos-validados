import re
import os
import time
import logging
import requests
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================
# 1. SETUP DE PASTAS SEGURO PARA .EXE
# ==============================================================
if getattr(sys, 'frozen', False):
    # Se estiver rodando como um executável (.exe)
    DIRETORIO_BASE = os.path.dirname(sys.executable)
else:
    # Se estiver rodando como script (.py) normal
    DIRETORIO_BASE = os.path.dirname(os.path.abspath(__file__))

# ==========================================
# CONFIGURACAO DE LOGS
# ==========================================
caminho_log = os.path.join(DIRETORIO_BASE, 'robo_cacador.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(caminho_log, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================================
# 🛡️ MÓDULO DE SEGURANÇA: VALIDAÇÃO GOOGLE SHEETS
# ==============================================================
def verificar_licenca(nome_robo):
    """Lê a matriz de controle no Google Sheets via CSV público."""
    url_painel = "https://docs.google.com/spreadsheets/d/SEU_PAINEL_ID/pub?output=csv"
    
    logger.info("==================================================")
    logger.info(f"📡 Consultando a Central da Diretoria: {nome_robo}...")
    
    try:
        resposta = requests.get(url_painel, timeout=10)
        resposta.raise_for_status() 
        texto_csv = resposta.text.upper()
        
        padrao_virgula = f"{nome_robo},ATIVO".upper()
        padrao_ponto_virgula = f"{nome_robo};ATIVO".upper()
        
        if (padrao_virgula in texto_csv) or (padrao_ponto_virgula in texto_csv):
            logger.info(f"✅ Licença validada! {nome_robo} autorizado via Control Room.\n")
            return True
        else:
            logger.error("==================================================")
            logger.error(f"⛔ ACESSO NEGADO: {nome_robo} encontra-se DESATIVADO no painel principal.")
            logger.error("==================================================")
            os.system("pause")
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        logger.error("==================================================")
        logger.error(f"⛔ ERRO DE CONEXÃO: Falha ao contatar o servidor de licenciamento.")
        logger.error("==================================================")
        os.system("pause")
        sys.exit(1)

# ==========================================
# 2. CARREGAMENTO DO COFRE (.ENV)
# ==========================================
env_path = os.path.join(DIRETORIO_BASE, ".env")
load_dotenv(env_path)

USUARIO = os.getenv("USUARIO") or os.getenv("F360_EMAIL")
SENHA = os.getenv("SENHA") or os.getenv("F360_PASSWORD")     
if not USUARIO or not SENHA:
    logger.error(f"❌ Erro: Credenciais não encontradas no arquivo .env em {env_path}")
    os.system("pause")
    sys.exit()

MODO_VARREDURA_MESES = 2 

import json

# Lista de tarefas para conciliacao (configuravel via tarefas_config.json ou variavel de ambiente)
DEFAULT_TAREFAS = [
    {"loja": "UNIDADE SHOPPING MATRIZ", "banco": "Banco 01 - CC 12345-6"},
    {"loja": "UNIDADE SHOPPING FILIAL A", "banco": "Banco 02 - CC 98765-4"},
    {"loja": "UNIDADE SHOPPING FILIAL B", "banco": "Banco 02 - CC 54321-0"},
]
CONFIG_FILE = os.path.join(DIRETORIO_BASE, "tarefas_config.json")
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f_cfg:
            TAREFAS = json.load(f_cfg)
    except Exception:
        TAREFAS = DEFAULT_TAREFAS
else:
    TAREFAS = DEFAULT_TAREFAS

class RoboFinanceiroCacador:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.acoes = None

    def gerar_lista_meses_alvo(self):
        hoje = datetime.now()
        meses_para_varrer = []
        if MODO_VARREDURA_MESES == 1:
            for mes in range(1, hoje.month + 1):
                dias_no_mes = (hoje.replace(month=mes % 12 + 1, day=1) - timedelta(days=1)).day if mes < 12 else 31
                dias_fim = dias_no_mes if mes != hoje.month else hoje.day
                meses_para_varrer.append({"mes_ano": f"{mes:02d}/{hoje.year}", "dias_fim": dias_fim})
        else:
            primeiro_dia_mes_atual = hoje.replace(day=1)
            ultimo_dia_mes_passado = primeiro_dia_mes_atual - timedelta(days=1)
            meses_para_varrer.append({"mes_ano": ultimo_dia_mes_passado.strftime("%m/%Y"), "dias_fim": ultimo_dia_mes_passado.day})
            meses_para_varrer.append({"mes_ano": hoje.strftime("%m/%Y"), "dias_fim": hoje.day})
        return meses_para_varrer

    def inicializar_driver(self):
        os.system("taskkill /f /im chromedriver.exe /T >nul 2>&1")
        try:
            options = Options()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-notifications")
            
            caminho_driver = ChromeDriverManager().install()
            
            import selenium
            if int(selenium.__version__.split('.')[0]) >= 4:
                service = Service(caminho_driver)
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                self.driver = webdriver.Chrome(executable_path=caminho_driver, options=options)
                
            self.wait = WebDriverWait(self.driver, 20)
            self.acoes = ActionChains(self.driver)
            logger.info("✅ Navegador iniciado!")
            return True
        except Exception as e:
            logger.error(f"Erro ao inicializar: {e}")
            return False

    def limpar_propagandas_f360(self):
        self.driver.execute_script("""
            document.querySelectorAll('#f360-campanha-modal-standard, .f360-campanha-modal-standard, .img-banner-h, .sweetalert, #intercom-container').forEach(e => e.remove());
            document.body.classList.remove('modal-open');
            document.querySelectorAll('.sweetalert button, .modal button').forEach(b => { if((b.innerText || '').includes('OK')) b.click(); });
        """)

    def fazer_login(self):
        try:
            logger.info("🔑 Acessando F360...")
            self.driver.get("https://financas.f360.com.br/")
            
            ipt_email = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[placeholder*='e-mail']")))
            ipt_senha = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], input[placeholder*='senha']")))
            
            ipt_email.clear()
            ipt_email.send_keys(USUARIO)
            ipt_senha.clear()
            ipt_senha.send_keys(SENHA)
            ipt_senha.send_keys(Keys.ENTER)
            try:
                btn_cont = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Continuar')]")))
                btn_cont.click()
            except: pass
                        # PROCURAR BOTÃO DE "CONTINUAR" PARA SESSÃO PRESA (LOOP INTELIGENTE)
            for _ in range(8):
                time.sleep(1.5)
                try:
                    clicou = self.driver.execute_script("""
                        var btns = document.querySelectorAll('button, a, .btn');
                        for(var i=0; i<btns.length; i++) {
                            var txt = (btns[i].innerText || '').trim().toUpperCase();
                            if (txt === 'CONTINUAR') {
                                btns[i].click();
                                return true;
                            }
                        }
                        return false;
                    """)
                    if clicou:
                        logger.info("    -> Botão 'Continuar' (sessão em andamento) detectado e clicado!")
                        break
                except: pass
            
            time.sleep(8) 
            return True
        except Exception as e:
            logger.error(f"Erro no login: {e}")
            return False

    def injetar_clique_humano(self, elemento, duplo=False):
        script = """
            var el = arguments[0]; var duplo = arguments[1];
            if(!el) return;
            el.scrollIntoView({block: 'center', behavior: 'instant'});
            var rect = el.getBoundingClientRect();
            var cx = rect.left + (rect.width / 2); var cy = rect.top + (rect.height / 2);
            var opts = {bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, buttons: 1};
            el.dispatchEvent(new MouseEvent('mouseover', opts));
            el.dispatchEvent(new MouseEvent('mousedown', opts));
            el.dispatchEvent(new MouseEvent('mouseup', opts));
            el.dispatchEvent(new MouseEvent('click', opts));
            try { el.click(); } catch(e) {}
            if (duplo) {
                setTimeout(function() {
                    el.dispatchEvent(new MouseEvent('dblclick', Object.assign({}, opts, {detail: 2})));
                }, 100);
            }
        """
        self.driver.execute_script(script, elemento, duplo)

    def extrair_dados_do_banco(self, banco_alvo):
        depositos_por_dia = {}
        try:
            logger.info(f"\n======================================")
            logger.info(f"🏦 FASE 1: LENDO EXTRATO BANCÁRIO")
            logger.info(f"Banco: {banco_alvo}")
            
            self.driver.get("https://financas.f360.com.br/ContasMovimento")
            time.sleep(8)
            self.limpar_propagandas_f360()
            
            # 1. GARANTE A ABA "CONCILIAÇÃO DE CONTAS"
            logger.info(" -> Selecionando aba 'Conciliação de Contas'...")
            self.driver.execute_script("""
                var abas = document.querySelectorAll('.nav-tabs a, .nav-tabs li, .k-tabstrip-items li, .k-link');
                for(var i=0; i<abas.length; i++) {
                    if((abas[i].innerText || '').trim().toUpperCase() === 'CONCILIAÇÃO DE CONTAS') {
                        if(abas[i].offsetParent !== null) {
                            abas[i].click();
                            return true;
                        }
                    }
                }
                return false;
            """)
            time.sleep(3)

            # 2. SELECIONA A CONTA
            clicou_conta = self.driver.execute_script("""
                var wraps = document.querySelectorAll('.k-dropdown-wrap, .k-combobox');
                for(var i=0; i<wraps.length; i++) {
                    if(wraps[i].offsetParent !== null) {
                        wraps[i].click(); 
                        return true;
                    }
                } return false;
            """)
            
            time.sleep(1.5)
            if clicou_conta:
                ipt_busca = self.driver.execute_script("""
                    var ipts = document.querySelectorAll('input.k-textbox');
                    for(var i=0; i<ipts.length; i++) {
                        if(ipts[i].offsetParent !== null) return ipts[i];
                    } 
                    var vis = document.querySelectorAll('input.k-input');
                    for(var i=0; i<vis.length; i++) {
                        if(vis[i].offsetParent !== null && !vis[i].readOnly) return vis[i];
                    }
                    return null;
                """)
                
                if ipt_busca:
                    conta_numero = banco_alvo.split('-', 1)[1].strip()
                    logger.info(f" -> Digitando conta: {conta_numero}")
                    ipt_busca.send_keys(Keys.CONTROL + 'a')
                    ipt_busca.send_keys(Keys.BACKSPACE)
                    time.sleep(0.5)
                    ipt_busca.send_keys(conta_numero)
                    time.sleep(3) 
                    
                    clicou_item = self.driver.execute_script(f"""
                        var alvo = "{banco_alvo}".trim().toUpperCase();
                        var listas = document.querySelectorAll('.k-list-container, .k-animation-container');
                        for(var i=0; i<listas.length; i++) {{
                            if(listas[i].style.display !== 'none') {{
                                var itens = listas[i].querySelectorAll('li');
                                for(var j=0; j<itens.length; j++) {{
                                    var texto = (itens[j].innerText || '').trim().toUpperCase();
                                    if(texto === alvo || (texto.includes(alvo) && !texto.includes('APLICAÇÃO'))) {{
                                        itens[j].scrollIntoView({{block: 'center'}});
                                        itens[j].click();
                                        return true;
                                    }}
                                }}
                            }}
                        }}
                        return false;
                    """)
                    
                    if not clicou_item:
                        ipt_busca.send_keys(Keys.ENTER)
            else:
                conta_numero = banco_alvo.split('-', 1)[1].strip()
                ActionChains(self.driver).send_keys(conta_numero).pause(2).send_keys(Keys.ENTER).perform()
            
            time.sleep(6)

            # =========================================================
            # NOVO: FORÇAR SELEÇÃO DE "PENDENTE DE CONCILIAÇÃO"
            # =========================================================
            logger.info(" -> Selecionando vista 'Pendente de conciliação'...")
            clicou_pendente = self.driver.execute_script("""
                var elementos = document.querySelectorAll('span, a, button, label, li, div');
                for(var i=0; i<elementos.length; i++) {
                    var txt = (elementos[i].innerText || '').trim().toUpperCase();
                    // Captura variações textuais comuns de estado pendente no F360
                    if(txt === 'PENDENTE DE CONCILIAÇÃO' || txt === 'PENDENTES DE CONCILIAÇÃO' || txt === 'PENDENTES') {
                        if(elementos[i].offsetParent !== null) {
                            elementos[i].scrollIntoView({block: 'center', behavior: 'instant'});
                            elementos[i].click();
                            return true;
                        }
                    }
                }
                return false;
            """)
            
            if clicou_pendente:
                logger.info("    ✅ Tela dividida acionada com sucesso.")
                time.sleep(4) # Pausa exigida para a requisição XHR dividir a interface
            else:
                logger.warning("    ⚠️ Filtro 'Pendente de conciliação' não localizado. O DOM pode ter mudado.")
            # =========================================================

            meses_para_varrer = self.gerar_lista_meses_alvo()
            
            for mes_info in meses_para_varrer:
                mes_alvo = mes_info["mes_ano"]
                dias_fim = mes_info["dias_fim"]
                
                logger.info(f" -> 📅 Processando mês: {mes_alvo}")
                try:
                    # 3. MUDA O MÊS DO CALENDÁRIO PRINCIPAL
                    script_mes = "var inputs = document.querySelectorAll('input.k-input'); for(var i=0;i<inputs.length;i++){ if(inputs[i].value && inputs[i].value.includes('/20')) return inputs[i]; } return null;"
                    campo_mes = self.driver.execute_script(script_mes)
                    if campo_mes:
                        self.driver.execute_script(f"""
                            var ipt = arguments[0];
                            var kDate = window.$(ipt).data('kendoDatePicker');
                            var partes = '{mes_alvo}'.split('/');
                            if(kDate) {{
                                kDate.value(new Date(parseInt(partes[1]), parseInt(partes[0])-1, 1));
                                kDate.trigger('change');
                            }} else {{
                                ipt.value = '01/{mes_alvo}';
                                ipt.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                ipt.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        """, campo_mes)
                        time.sleep(0.5)
                        try:
                            campo_mes.send_keys(Keys.ENTER)
                            campo_mes.send_keys(Keys.TAB)
                        except: pass
                        time.sleep(3)
                except:
                    pass
                
                # 4. ABRIR A GAVETA CLICANDO NO DIA 1 DO CALENDÁRIO PRINCIPAL
                abriu_detalhe = self.driver.execute_script(f"""
                    var tds = document.querySelectorAll("td, .fc-day-top");
                    for(var i=0; i<tds.length; i++) {{
                        var d = tds[i].getAttribute('data-date');
                        if(d && d.endsWith("-01")) {{
                            var alvo_clique = tds[i];
                            var num = tds[i].querySelector('.fc-day-number');
                            if (num) alvo_clique = num;
                            alvo_clique.scrollIntoView({{block: 'center', behavior: 'instant'}});
                            var rect = alvo_clique.getBoundingClientRect();
                            var cx = rect.left + (rect.width / 2);
                            var cy = rect.top + (rect.height / 2);
                            var opts = {{bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, buttons: 1}};
                            alvo_clique.dispatchEvent(new MouseEvent('mouseover', opts));
                            alvo_clique.dispatchEvent(new MouseEvent('mousedown', opts));
                            alvo_clique.dispatchEvent(new MouseEvent('mouseup', opts));
                            alvo_clique.dispatchEvent(new MouseEvent('click', opts));
                            try {{ alvo_clique.click(); }} catch(e) {{}}
                            setTimeout(function() {{
                                alvo_clique.dispatchEvent(new MouseEvent('dblclick', Object.assign({{}}, opts, {{detail: 2}})));
                            }}, 100);
                            return true;
                        }}
                    }}
                    return false;
                """)
                
                time.sleep(4)
                if not abriu_detalhe:
                    logger.warning(f"Não conseguiu abrir o calendário para {mes_alvo}. Pulando para o próximo.")
                    continue
                
                # 5. DENTRO DO MODAL ABERTO, VARRER OS DIAS
                for dia in range(1, dias_fim + 1):
                    data_pt = f"{dia:02d}/{mes_alvo}"
                    
                    try:
                        mudou_data = self.driver.execute_script(f"""
                            var modais = document.querySelectorAll('.k-window');
                            var container = document;
                            for(var m=0; m<modais.length; m++) {{
                                if(modais[m].style.display !== 'none') {{
                                    container = modais[m]; break;
                                }}
                            }}
                            var inputs = container.querySelectorAll("input");
                            var dates = [];
                            for(var i=0; i<inputs.length; i++) {{
                                if(inputs[i].offsetParent !== null && (inputs[i].classList.contains('datepicker') || inputs[i].className.includes('hasDatepicker') || inputs[i].getAttribute('data-role') === 'datepicker' || (inputs[i].value && inputs[i].value.match(/\\d{{2}}\\/\\d{{2}}\\/\\d{{4}}/)))) {{
                                    dates.push(inputs[i]);
                                }}
                            }}
                            if(dates.length > 0) {{
                                var target = dates[dates.length - 1]; 
                                var kDate = window.$(target).data('kendoDatePicker');
                                var partes = '{data_pt}'.split('/'); 
                                if(kDate) {{
                                    kDate.value(new Date(parseInt(partes[2]), parseInt(partes[1])-1, parseInt(partes[0])));
                                    kDate.trigger('change');
                                }} else {{
                                    target.value = '{data_pt}';
                                    target.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    target.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                }}
                                target.setAttribute('id', 'id_data_ext_temp');
                                return true;
                            }}
                            return false;
                        """)
                        
                        if mudou_data:
                            try:
                                campo = self.driver.find_element(By.ID, "id_data_ext_temp")
                                campo.send_keys(Keys.ENTER)
                                time.sleep(0.1)
                                campo.send_keys(Keys.TAB)
                                self.driver.execute_script("arguments[0].removeAttribute('id');", campo)
                            except: pass
                            
                            time.sleep(1)
                            for _ in range(10):
                                tem_loading = self.driver.execute_script("return document.querySelectorAll('.k-loading-mask, .k-loading-image').length > 0;")
                                if not tem_loading:
                                    break
                                time.sleep(0.5)
                            time.sleep(0.5)
                            
                    except Exception as e:
                        logger.error(f"Erro ao mudar data para {data_pt}: {e}")
                    
                    texto_tela = self.driver.execute_script("""
                        var modais = document.querySelectorAll('.k-window');
                        var container = document.body;
                        for(var m=0; m<modais.length; m++) {
                            if(modais[m].style.display !== 'none') {
                                container = modais[m]; break;
                            }
                        }
                        return container.innerText.replace(/\\n/g, '  ');
                    """).upper()
                    
                    texto_limpo = texto_tela.replace('-R$', 'MENOS_RS')
                    pedacos = texto_limpo.split('R$')
                    
                    for pedaco in pedacos[1:]:
                        match_valor = re.search(r"^\s*([\d\.,]+)", pedaco)
                        if match_valor:
                            valor_str = match_valor.group(1).replace('.', '').replace(',', '.')
                            
                            contexto = pedaco[:250] 
                            eh_deposito = bool(re.search(r'(DEP.*DINH|DP\s*DIN|ESP[EÉ]CIE)', contexto))
                            
                            if eh_deposito and float(valor_str) > 0:
                                if data_pt not in depositos_por_dia: depositos_por_dia[data_pt] = []
                                depositos_por_dia[data_pt].append(float(valor_str))
                                logger.info(f"   💸 [ACHOU] R$ {valor_str} em {data_pt}")
                
                # 6. FECHA O MODAL ANTES DE IR PARA O PRÓXIMO MÊS
                self.driver.execute_script("""
                    var modais = document.querySelectorAll('.k-window');
                    for(var m=0; m<modais.length; m++) {
                        if(modais[m].style.display !== 'none') {
                            var btn_close = modais[m].querySelector('.k-window-actions .k-i-close, .close');
                            if(btn_close) {
                                btn_close.click();
                            } else {
                                modais[m].style.display = 'none';
                            }
                        }
                    }
                    document.querySelectorAll('.k-overlay').forEach(e => e.remove());
                """)
                time.sleep(2)
                
            total_itens = sum(len(v) for v in depositos_por_dia.values())
            logger.info(f"📊 Fim da leitura. {total_itens} depósitos encontrados.")
            return depositos_por_dia
        except Exception as e:
            logger.error(f"❌ Erro na extração: {e}")
            return {}

    def processar_loja_no_fechamento(self, loja_alvo, banco_alvo, depositos_por_dia):
        logger.info(f"\n======================================")
        logger.info(f"🛒 FASE 2: LANÇANDO NA LOJA")
        logger.info(f"Loja: {loja_alvo}")
        datas_ordenadas = sorted(depositos_por_dia.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y"))
        if not datas_ordenadas:
            return
            
        try:
            self.driver.get("https://financas.f360.com.br/FechamentoDeCaixa")
        except Exception as e:
            if "timeout" in str(e).lower():
                logger.warning("    ⚠️ F360 demorou a carregar. Forçando parada e prosseguindo...")
                self.driver.execute_script("window.stop();")
            else:
                logger.error(f"Erro ao acessar Fechamento de Caixa: {e}")
                return
                
        time.sleep(10) 
        
        self.driver.execute_script("""
            try {
                document.querySelectorAll('.sweetalert, #intercom-container, .f360-campanha-modal-standard, .img-banner-h').forEach(e => e.remove());
                document.body.classList.remove('modal-open');
            } catch(e) {}
        """)
        
        logger.info("    -> Selecionando a loja...")
        try:
            caixa = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span.k-widget.k-combobox")))
            self.injetar_clique_humano(caixa, duplo=False)
            time.sleep(1)
            
            ipt = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.k-input[role='combobox']")))
            ipt.clear()
            ipt.send_keys(loja_alvo)
            time.sleep(3) 
            ipt.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.5)
            ipt.send_keys(Keys.ENTER)
            time.sleep(1)
            time.sleep(4)
        except Exception as e:
            logger.error(f"    ❌ Dropdown da Empresa não encontrado na tela de Fechamento: {e}")
            return
            
        mes_ano_atual_no_calendario = None
        for data_pt in datas_ordenadas:
            valores_do_dia = depositos_por_dia[data_pt]
            dia_alvo_str = data_pt.split('/')[0].lstrip('0')
            mes_ano_alvo = data_pt[3:]
            data_obj = datetime.strptime(data_pt, "%d/%m/%Y")
            logger.info(f" -> Dia {data_pt} tem {len(valores_do_dia)} depósito(s). Carregando calendário...")
            
            try:
                if mes_ano_atual_no_calendario != mes_ano_alvo:
                    script_mes = "var inputs = document.querySelectorAll('input.k-input'); for(var i=0;i<inputs.length;i++){ if(inputs[i].value && inputs[i].value.includes('/20')) return inputs[i]; } return null;"
                    campo_mes = self.driver.execute_script(script_mes)
                    if campo_mes:
                        self.driver.execute_script(f"""
                            var ipt = arguments[0];
                            var kDate = window.$(ipt).data('kendoDatePicker');
                            var partes = '{mes_ano_alvo}'.split('/');
                            if(kDate) {{
                                kDate.value(new Date(parseInt(partes[1]), parseInt(partes[0])-1, 1));
                                kDate.trigger('change');
                            }} else {{
                                ipt.value = '01/{mes_ano_alvo}';
                                ipt.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                ipt.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        """, campo_mes)
                        time.sleep(0.5)
                        try:
                            campo_mes.send_keys(Keys.ENTER)
                            campo_mes.send_keys(Keys.TAB)
                        except: pass
                        time.sleep(5)
                        mes_ano_atual_no_calendario = mes_ano_alvo
                        
                def tentar_abrir_gaveta(data_alvo_iso, d_str):
                    try:
                        # 1. Clicar no dia no calendário principal visível (Ignorando o mini-calendário escondido)
                        clicou_dia = self.driver.execute_script(f"""
                            var celulas = document.querySelectorAll('td.day, td.fc-day-top, td[data-date]');
                            for (var i = 0; i < celulas.length; i++) {{
                                var c = celulas[i];
                                if (c.offsetParent !== null && !c.closest('.k-calendar') && !c.classList.contains('empty') && !c.classList.contains('k-other-month')) {{
                                    var dDate = c.getAttribute('data-date');
                                    var txt = (c.innerText || '').trim().split('\\n')[0];
                                    
                                    if (dDate === '{data_alvo_iso}' || txt === '{d_str}') {{
                                        c.scrollIntoView({{block: 'center', behavior: 'instant'}});
                                        
                                        var rect = c.getBoundingClientRect();
                                        var cx = rect.left + (rect.width/2);
                                        var cy = rect.top + (rect.height/2);
                                        var opts = {{bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, buttons: 1}};
                                        
                                        c.dispatchEvent(new MouseEvent('mouseover', opts));
                                        c.dispatchEvent(new MouseEvent('mousedown', opts));
                                        c.dispatchEvent(new MouseEvent('mouseup', opts));
                                        c.dispatchEvent(new MouseEvent('click', opts));
                                        
                                        setTimeout(function(){{
                                            c.dispatchEvent(new MouseEvent('dblclick', Object.assign({{}}, opts, {{detail: 2}})));
                                        }}, 150);
                                        
                                        return true;
                                    }}
                                }}
                            }}
                            return false;
                        """)
                        
                        if not clicou_dia:
                            return False
                            
                        time.sleep(6) 
                        
                        # 2. Expandir a aba 'Depósitos'
                        self.driver.execute_script("""
                            var divs = document.querySelectorAll('div');
                            for(var i=0; i<divs.length; i++) {
                                if(divs[i].innerText && divs[i].innerText.startsWith('Depósitos')) {
                                    var icon = divs[i].querySelector('.fa-plus, .fa-caret-right');
                                    if(icon || divs[i].classList.contains('collapsed')) {
                                        divs[i].scrollIntoView({block:'center'});
                                        divs[i].click(); 
                                    }
                                }
                            }
                        """)
                        time.sleep(2)
                        
                        # 3. Clicar em "+ Adicionar"
                        btn_add = self.driver.execute_script("""
                            var btn_bind = document.querySelector("[data-bind*='FazerDepositos.Open']");
                            if(btn_bind && btn_bind.offsetParent !== null) {
                                btn_bind.scrollIntoView({block:'center'});
                                btn_bind.click();
                                return true;
                            }
                            var spans = document.querySelectorAll('span, a, button');
                            for (var i = 0; i < spans.length; i++) {
                                if ((spans[i].innerText || '').trim() === '+ Adicionar' && spans[i].offsetParent !== null) {
                                    var pai = spans[i].closest('div, .row, tr');
                                    if (pai && (pai.innerText || '').includes('Depósitos') && !(pai.innerText || '').includes('Despesas')) {
                                        spans[i].scrollIntoView({block: 'center'});
                                        spans[i].click();
                                        return true;
                                    }
                                }
                            }
                            return false;
                        """)
                        
                        if btn_add:
                            time.sleep(3)
                            labels = self.driver.find_elements(By.XPATH, "//div[not(contains(@style, 'display: none'))]//label[contains(text(),'Valor do Depósito')]")
                            if any(lbl.is_displayed() for lbl in labels):
                                return True
                            else:
                                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                time.sleep(1)
                                return False
                        else:
                            return False
                            
                    except Exception as err:
                        return False
                    
                logger.info("    -> Procurando a gaveta no calendário...")
                status_gaveta = False
                for dias_para_voltar in range(5): 
                    data_tentativa_obj = data_obj - timedelta(days=dias_para_voltar)
                    data_tentativa_iso = data_tentativa_obj.strftime("%Y-%m-%d")
                    dia_tentativa_str = str(data_tentativa_obj.day)
                    
                    if dias_para_voltar > 0:
                        logger.info(f"    ⚠️ Sem botão de Adicionar. Plano B: Abrindo pelo dia {data_tentativa_obj.strftime('%d/%m/%Y')}...")
                        
                    status_gaveta = tentar_abrir_gaveta(data_tentativa_iso, dia_tentativa_str)
                    if status_gaveta: 
                        break
                        
                if not status_gaveta:
                    logger.error(f"    ❌ A gaveta não abriu nem no dia {data_pt} nem nos dias anteriores.")
                    continue
                    
                for idx, valor_float in enumerate(valores_do_dia):
                    eh_ultimo = (idx == len(valores_do_dia) - 1)
                    valor_str = f"{valor_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                    logger.info(f"      -> Injetando na esteira: R$ {valor_str}...")
                    
                    self.driver.execute_script("""
                        document.querySelectorAll('button, a').forEach(b => {
                            if(b.offsetParent !== null && (b.innerText || '').trim().toUpperCase() === 'OK') b.click();
                        });
                        document.querySelectorAll('.k-loading-mask, .k-overlay, .sweet-alert, .sweetalert').forEach(e => e.remove());
                    """)
                    time.sleep(1)
                    
                    xpath_visivel = "//div[not(contains(@style, 'display: none'))]//label[contains(text(),'Valor do Depósito')]/following::input[not(@type='hidden')][1]"
                    try:
                        campo_valor = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_visivel)))
                    except Exception as e:
                        logger.error(f"    ❌ Não conseguiu encontrar o campo Valor do Depósito.")
                        continue
                        
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", campo_valor)
                    time.sleep(0.3)
                    self.injetar_clique_humano(campo_valor, duplo=False)
                    time.sleep(0.3)
                    
                    campo_valor_real = self.driver.execute_script("""
                        var fake = arguments[0];
                        var container = fake.closest('.k-numerictextbox');
                        if(container) {
                            var real = container.querySelector('input[data-role="numerictextbox"]');
                            if(real) {
                                fake.style.display = 'none';
                                real.style.display = 'inline-block';
                                return real;
                            }
                        }
                        return fake;
                    """, campo_valor)
                    
                    campo_valor_real.send_keys(Keys.END)
                    time.sleep(0.1)
                    for _ in range(15): 
                        campo_valor_real.send_keys(Keys.BACKSPACE)
                        campo_valor_real.send_keys(Keys.DELETE)
                    time.sleep(0.2)
                    
                    for digito in str(valor_str):
                        campo_valor_real.send_keys(digito)
                        time.sleep(0.05)
                        
                    time.sleep(0.3)
                    
                    try:
                        data_limpa = data_pt.replace('/', '') 
                        xpath_data_deposito = "//div[not(contains(@style, 'display: none'))]//label[contains(text(), 'Data do Depósito')]/following::input[1]"
                        campo_data_dep = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_data_deposito)))
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", campo_data_dep)
                        time.sleep(0.3)
                        self.injetar_clique_humano(campo_data_dep, duplo=False)
                        time.sleep(0.3)
                        
                        campo_data_dep.send_keys(Keys.END)
                        for _ in range(12): campo_data_dep.send_keys(Keys.BACKSPACE)
                        for char in data_limpa:
                            campo_data_dep.send_keys(char)
                            time.sleep(0.05)
                        time.sleep(0.3)
                        
                        xpath_data_credito = "//div[not(contains(@style, 'display: none'))]//label[contains(text(), 'Data do Crédito')]/following::input[1]"
                        campo_data_cred = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_data_credito)))
                        self.injetar_clique_humano(campo_data_cred, duplo=False)
                        time.sleep(0.3)
                        
                        campo_data_cred.send_keys(Keys.END)
                        for _ in range(12): campo_data_cred.send_keys(Keys.BACKSPACE)
                        for char in data_limpa:
                            campo_data_cred.send_keys(char)
                            time.sleep(0.05)
                        time.sleep(0.3)
                    except Exception as e:
                        logger.warning(f"      ⚠️ Aviso: Erro ao digitar data fisicamente (tentando via JS fallback)")
                        
                    self.driver.execute_script(f"""
                        var modais = document.querySelectorAll('.k-window');
                        for(var m=0; m<modais.length; m++) {{
                            if (modais[m].style.display !== 'none') {{ 
                                var ipt = modais[m].querySelector('input[data-role="numerictextbox"]');
                                if(ipt && window.$(ipt).data("kendoNumericTextBox")) {{ 
                                    window.$(ipt).data("kendoNumericTextBox").value({valor_float}); 
                                    window.$(ipt).data("kendoNumericTextBox").trigger("change"); 
                                }}
                                var dt_inputs = modais[m].querySelectorAll('input[data-role="datepicker"], input.hasDatepicker');
                                for(var i=0; i<dt_inputs.length; i++) {{
                                    var kDate = window.$(dt_inputs[i]).data("kendoDatePicker");
                                    if(kDate) {{
                                        var partes = '{data_pt}'.split('/');
                                        kDate.value(new Date(partes[2], parseInt(partes[1])-1, partes[0]));
                                        kDate.trigger("change");
                                    }}
                                }}
                            }}
                        }}
                    """)
                    time.sleep(1.5)
                    
                    try:
                        xpath_input_banco = "//div[not(contains(@style, 'display: none'))]//label[contains(text(), 'Conta de Destino')]/following::input[@role='combobox'][1]"
                        campo_banco = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input_banco)))
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo_banco)
                        time.sleep(0.3)
                        self.injetar_clique_humano(campo_banco, duplo=False)
                        time.sleep(0.5)
                        
                        campo_banco.send_keys(Keys.CONTROL + 'a')
                        campo_banco.send_keys(Keys.BACKSPACE)
                        time.sleep(0.5) 
                        
                        conta_numero = banco_alvo.split('-', 1)[1].strip()
                        logger.info(f"      -> Digitando conta de destino: {conta_numero}")
                        for char in conta_numero:
                            campo_banco.send_keys(char)
                            time.sleep(0.1) 
                        
                        time.sleep(3) 
                        
                        clicou_item = self.driver.execute_script(f"""
                            var alvo = "{banco_alvo}".trim().toUpperCase();
                            var listas = document.querySelectorAll('.k-list-container, .k-animation-container');
                            for(var i=0; i<listas.length; i++) {{
                                if(listas[i].style.display !== 'none') {{
                                    var itens = listas[i].querySelectorAll('li');
                                    for(var j=0; j<itens.length; j++) {{
                                        var texto = (itens[j].innerText || '').trim().toUpperCase();
                                        if(texto === alvo || (texto.includes(alvo) && !texto.includes('APLICAÇÃO'))) {{
                                            itens[j].scrollIntoView({{block: 'center'}});
                                            itens[j].click();
                                            return true;
                                        }}
                                    }}
                                }}
                            }}
                            return false;
                        """)
                        if not clicou_item:
                            campo_banco.send_keys(Keys.ENTER)
                        time.sleep(1.5)
                    except Exception as err:
                        logger.error(f"Falha ao selecionar banco destino: {err}")
                        
                    if eh_ultimo:
                        logger.info("      -> Último valor da fila. Salvando e fechando o modal...")
                        salvou_popup = self.driver.execute_script("""
                            var btns = document.querySelectorAll('button, a, input');
                            var alvo = null;
                            for(var j=0; j<btns.length; j++) {
                                var txt = (btns[j].innerText || btns[j].value || '').trim().toLowerCase();
                                if(txt === 'salvar' && btns[j].offsetParent !== null) {
                                    alvo = btns[j];
                                }
                            }
                            if(alvo) {
                                alvo.scrollIntoView({block: 'center'});
                                alvo.click();
                                return true;
                            }
                            return false;
                        """)
                        
                        if not salvou_popup:
                            xpath_btn_salvar = "//button[normalize-space(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))='salvar']"
                            try:
                                btns_s = self.wait.until(EC.presence_of_all_elements_located((By.XPATH, xpath_btn_salvar)))
                                for b in reversed(btns_s):
                                    if b.is_displayed():
                                        self.injetar_clique_humano(b, duplo=False)
                                        break
                            except:
                                try:
                                    btns_s = self.driver.find_elements(By.XPATH, xpath_btn_salvar)
                                    for b in reversed(btns_s):
                                        if b.is_displayed():
                                            self.driver.execute_script("arguments[0].click();", b)
                                            break
                                except Exception as inner_e:
                                    logger.error(f"      ❌ Erro ao encontrar botão Salvar: {inner_e}")
                        time.sleep(5)
                        
                        alerta_erro = self.driver.execute_script("""
                            try {
                                var txt = document.body.innerText || '';
                                if(txt.includes('Ocorreu um erro') || txt.includes('obrigatório')) {
                                    var btns = document.querySelectorAll('button, a');
                                    for(var b=0; b<btns.length; b++) { if((btns[b].innerText||'').includes('OK')) btns[b].click(); }
                                    return true;
                                } return false;
                            } catch(e) { return false; }
                        """)
                        if alerta_erro:
                            logger.error("      ❌ Servidor do F360 travou ao tentar salvar (Erro Vermelho).")
                            continue
                        
                        self.driver.execute_script("""
                            document.querySelectorAll('button, a').forEach(b => {
                                if(b.offsetParent !== null && (b.innerText || '').trim().toUpperCase() === 'OK') b.click();
                            });
                            document.querySelectorAll('.k-loading-mask, .k-overlay, .sweet-alert, .sweetalert').forEach(e => e.remove());
                        """)
                        
                        try:
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            time.sleep(1)
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                        except: pass
                        logger.info("      ✅ Depósito salvo com sucesso!")
                    else:
                        logger.info("      -> Mais valores em espera. Acionando 'Salvar e Criar Novo'...")
                        salvou_novo = self.driver.execute_script("""
                            var btns = document.querySelectorAll('button, a, input');
                            for(var j=0; j<btns.length; j++) {
                                var txt = (btns[j].innerText || btns[j].value || '').trim().toLowerCase();
                                if((txt === 'salvar e criar novo' || txt === 'salvar e novo' || txt === 'salvar e criar') && btns[j].offsetParent !== null) {
                                    btns[j].scrollIntoView({block: 'center'});
                                    btns[j].click();
                                    return true;
                                }
                            }
                            return false;
                        """)
                        
                        if not salvou_novo:
                            xpath_btn_novo = "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'salvar e criar novo') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'salvar e novo')]"
                            try:
                                btn_n_elem = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_btn_novo)))
                                self.injetar_clique_humano(btn_n_elem, duplo=False)
                            except:
                                try:
                                    btns_novo = self.driver.find_elements(By.XPATH, xpath_btn_novo)
                                    for b in btns_novo:
                                        if b.is_displayed():
                                            self.driver.execute_script("arguments[0].click();", b)
                                            break
                                except Exception as inner_e:
                                    logger.error(f"      ❌ Erro ao encontrar botão Salvar e Criar Novo: {inner_e}")
                        time.sleep(5)
                        
                        self.driver.execute_script("""
                            document.querySelectorAll('button, a').forEach(b => {
                                if(b.offsetParent !== null && (b.innerText || '').trim().toUpperCase() === 'OK') b.click();
                            });
                            document.querySelectorAll('.k-loading-mask, .k-overlay, .sweet-alert, .sweetalert').forEach(e => e.remove());
                        """)
                        time.sleep(1)
                        logger.info("      ✅ Depósito salvo com sucesso! Seguindo para o próximo...")
                
                self.driver.execute_script("""
                    document.querySelectorAll('button.close, .btn-close, .modal-header .close').forEach(b => {
                        if(b.offsetParent !== null) b.click();
                    });
                """)
                time.sleep(2)
            except Exception as e:
                logger.error(f"    ❌ Erro no fechamento do dia {data_pt}: {e}")

    def executar(self):
        logger.info("\n==================================================")
        logger.info("🕵️‍♀️ ROBÔ CAÇADOR INICIADO")
        logger.info("==================================================")
        try:
            if not self.inicializar_driver(): return False
            if not self.fazer_login(): return False
            
            for tarefa in TAREFAS:
                loja_alvo = tarefa['loja']
                banco_alvo = tarefa['banco']
                
                depositos_por_dia = self.extrair_dados_do_banco(banco_alvo)
                if not depositos_por_dia:
                    logger.info(f"⏩ Pulando loja {loja_alvo} (Sem novos depósitos).")
                    continue
                
                self.processar_loja_no_fechamento(loja_alvo, banco_alvo, depositos_por_dia)
                
            logger.info("\n🏁 PROCESSO TOTALMENTE FINALIZADO!")
            return True
        except Exception as e:
            logger.error(f"[ERRO GERAL] Falha no robô: {e}")
            return False
        finally:
            if self.driver: 
                time.sleep(5)
                self.driver.quit()

# ==============================================================
# PONTO DE IGNIÇÃO
# ==============================================================
if __name__ == "__main__":
    verificar_licenca("ROBO_SANTANDER")
    
    robo = RoboFinanceiroCacador()
    robo.executar()