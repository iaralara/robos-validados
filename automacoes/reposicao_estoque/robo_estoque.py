import os
import glob
import time
import shutil
import traceback
import sys
import requests
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ============================================================================
#  CONFIGURACOES DE PASTAS
# ============================================================================
DIRETORIO_BASE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    DIRETORIO_BASE = os.path.dirname(sys.executable)

PASTA_DOWNLOAD_CIGAM = r"C:\Users\usuario_padrao\Desktop\Ligar\Reposição PINS"
PASTA_DOWNLOADS_PADRAO = os.path.join(os.path.expanduser("~"), "Downloads")

os.makedirs(PASTA_DOWNLOAD_CIGAM, exist_ok=True)

# ============================================================================
#  CREDENCIAIS CIGAM
# ============================================================================
load_dotenv()
CIGAM_ACESSO = os.getenv("CIGAM_ACESSO")
CIGAM_USER = os.getenv("CIGAM_USER")
CIGAM_SENHA = os.getenv("CIGAM_SENHA")

if not all([CIGAM_ACESSO, CIGAM_USER, CIGAM_SENHA]):
    raise ValueError("Credenciais CIGAM ausentes. Verifique o arquivo .env.")

# ============================================================================
#  LICENCA - GOOGLE SHEETS
# ============================================================================
def verificar_licenca(nome_robo):
    url_painel = "https://docs.google.com/spreadsheets/d/SEU_PAINEL_ID/pub?output=csv"
    try:
        resposta = requests.get(url_painel, timeout=10)
        resposta.raise_for_status()
        texto_csv = resposta.text.upper()
        padrao_virgula = f"{nome_robo},ATIVO".upper()
        padrao_ponto_virgula = f"{nome_robo};ATIVO".upper()
        if (padrao_virgula in texto_csv) or (padrao_ponto_virgula in texto_csv):
            print(f"Licenca validada: {nome_robo} autorizado via Control Room.")
            return True
        else:
            print("=" * 70)
            print(f"ACESSO NEGADO: {nome_robo} encontra-se DESATIVADO no painel principal.")
            print("=" * 70)
            os.system("pause")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print("=" * 70)
        print(f"ERRO DE CONEXAO: Falha ao contatar o servidor de licenciamento.")
        print(f"Detalhe tecnico: {e}")
        print("=" * 70)
        os.system("pause")
        sys.exit(1)

# ============================================================================
#  FUNCOES AUXILIARES
# ============================================================================
def clique_forcado(driver, xpath, descricao="elemento"):
    try:
        elemento = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", elemento)
        print(f"  OK: {descricao}")
        return True
    except Exception as e:
        print(f"  FALHA: {descricao}")
        return False

def tentar_clicar_multiplo(driver, xpaths, descricao):
    for xpath in xpaths:
        if clique_forcado(driver, xpath, descricao):
            return True
    return False

def scan_e_clicar(driver, texto_alvo, tag="span"):
    try:
        elementos = driver.find_elements(By.TAG_NAME, tag)
        for elem in elementos:
            if texto_alvo.upper() in elem.text.upper():
                driver.execute_script("arguments[0].click();", elem)
                print(f"  OK: {texto_alvo} encontrado por scan - '{elem.text.strip()}'")
                return True
    except Exception as e:
        print(f"  Scan falhou: {e}")
    return False

def clicar_elemento_por_texto(driver, texto, max_tentativas=5):
    texto_upper = texto.upper().strip()
    for tentativa in range(max_tentativas):
        seletores = [
            f"//li[contains(@class, 'nav-item')]//a[contains(text(), '{texto}')]",
            f"//li[contains(@class, 'nav-item')]//span[contains(text(), '{texto}')]",
            f"//a[contains(@class, 'nav-link') and contains(text(), '{texto}')]",
            f"//button[contains(text(), '{texto}')]",
            f"//span[contains(text(), '{texto}') and contains(@class, 'nav')]",
            f"//div[contains(@class, 'nav')]//span[contains(text(), '{texto}')]",
            f"//div[contains(@class, 'tab')]//span[contains(text(), '{texto}')]",
            f"//*[contains(text(), '{texto}') and not(contains(@class, 'dropdown'))]",
        ]
        for xpath in seletores:
            try:
                elementos = driver.find_elements(By.XPATH, xpath)
                for elem in elementos:
                    if elem.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", elem)
                        print(f"  OK: {texto} clicado (tentativa {tentativa + 1})")
                        return True
            except:
                continue
        try:
            resultado = driver.execute_script(
                "var todos = document.querySelectorAll('li, a, span, button, div');"
                "for (var i = 0; i < todos.length; i++) {"
                "    if (todos[i].textContent && todos[i].textContent.trim().toUpperCase() === '" + texto_upper + "') {"
                "        todos[i].click();"
                "        return 'Clicado via JS: ' + todos[i].tagName;"
                "    }"
                "}"
                "for (var i = 0; i < todos.length; i++) {"
                "    if (todos[i].textContent && todos[i].textContent.toUpperCase().includes('" + texto_upper + "')) {"
                "        todos[i].click();"
                "        return 'Fallback clicado: ' + todos[i].tagName;"
                "    }"
                "}"
                "return 'Nao encontrado';"
            )
            if 'Clicado' in resultado:
                print(f"  OK: {texto} - {resultado}")
                return True
        except:
            pass
        time.sleep(2)
    print(f"  FALHA: Nao conseguiu clicar em '{texto}' apos {max_tentativas} tentativas")
    return False

def expandir_e_selecionar_item_arvore(driver, texto_pai):
    print(f"\n[Expandindo/selecionando {texto_pai}...]")
    for tentativa in range(3):
        try:
            elementos = driver.find_elements(By.XPATH, f"//*[contains(text(), '{texto_pai}')]")
            for elem in elementos:
                if not elem.is_displayed():
                    continue
                pai = driver.execute_script(
                    "var el = arguments[0];"
                    "var li = el.closest('li, .rct-node, [class*=node], [class*=item]');"
                    "if (!li) li = el.parentElement;"
                    "for (var i = 0; i < 5; i++) {"
                    "    if (li && (li.tagName === 'LI' || (li.className && li.className.indexOf('node') >= 0) || (li.className && li.className.indexOf('item') >= 0))) break;"
                    "    if (li) li = li.parentElement;"
                    "}"
                    "return li;", elem
                )
                if pai:
                    btn_expandir = driver.execute_script(
                        "var li = arguments[0];"
                        "var btn = li.querySelector('button.rct-collapse-btn, .rct-collapse, [class*=expand], [class*=toggle]');"
                        "if (!btn) {"
                        "    var icons = li.querySelectorAll('i, svg, span, button');"
                        "    for (var i = 0; i < icons.length; i++) {"
                        "        var el = icons[i];"
                        "        var cls = (el.className && el.className.baseVal) ? el.className.baseVal : (el.className || '');"
                        "        var txt = el.textContent || el.innerText || '';"
                        "        if (cls.indexOf('plus') >= 0 || cls.indexOf('expand') >= 0 || cls.indexOf('chevron') >= 0 || "
                        "            cls.indexOf('toggle') >= 0 || cls.indexOf('caret') >= 0 || cls.indexOf('arrow') >= 0 ||"
                        "            txt.indexOf('+') >= 0 || txt.indexOf('▶') >= 0 || txt.indexOf('▼') >= 0) {"
                        "            return el;"
                        "        }"
                        "    }"
                        "}"
                        "return btn;", pai
                    )
                    if btn_expandir:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_expandir)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", btn_expandir)
                        print(f"  OK: {texto_pai} expandido via botao + (tentativa {tentativa + 1})")
                        return True
                    else:
                        driver.execute_script("arguments[0].click();", elem)
                        print(f"  OK: {texto_pai} clicado diretamente")
                        return True
        except Exception as e:
            print(f"  Tentativa {tentativa + 1} falhou: {e}")
            time.sleep(2)
    try:
        resultado = driver.execute_script(
            "var spans = document.querySelectorAll('span, div, td, label');"
            "for (var i = 0; i < spans.length; i++) {"
            "    if (spans[i].textContent && spans[i].textContent.toUpperCase().includes('" + texto_pai.upper() + "')) {"
            "        var li = spans[i].closest('li, .rct-node, tr, [class*=node], [class*=item]');"
            "        if (li) {"
            "            var btn = li.querySelector('button, .rct-collapse-btn, [class*=expand], [class*=toggle]');"
            "            if (btn) {"
            "                btn.click();"
            "                return 'Expandido via JS: ' + (btn.className || btn.tagName);"
            "            }"
            "            spans[i].click();"
            "            return 'Clicado direto: ' + spans[i].textContent;"
            "        }"
            "    }"
            "}"
            "return 'Nao encontrado';"
        )
        print(f"  OK: {resultado}")
        return True
    except Exception as e:
        print(f"  JS falhou: {e}")
    print(f"  AVISO: Nao conseguiu expandir {texto_pai}")
    return False

def selecionar_todas_lojas(driver):
    print("  [Selecionando todas as lojas...]")
    try:
        print("  [Expandindo arvore de lojas...]")
        botoes_expandir = driver.find_elements(By.XPATH,
            "//button[contains(@class, 'rct-collapse-btn')] | "
            + "//*[contains(@class, 'rct-collapse')] | "
            + "//i[contains(@class, 'fa-chevron') or contains(@class, 'bi-chevron') or contains(@class, 'arrow')] | "
            + "//span[contains(@class, 'rct-collapse')]"
        )
        for btn in botoes_expandir:
            try:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.3)
            except:
                pass
        
        btn_todas = driver.find_elements(By.XPATH,
            "//button[contains(text(), 'Todas') or contains(text(), 'Todos') or contains(text(), 'Selecionar')] | "
            + "//input[@type='checkbox'][following::*[contains(text(), 'Todas') or contains(text(), 'Todos')]] | "
            + "//span[contains(text(), 'Todas') or contains(text(), 'Todos')]/preceding::input[@type='checkbox'][1]"
        )
        for btn in btn_todas:
            try:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    print("  OK: Botao 'Todas' clicado")
                    return True
            except:
                pass
        
        print("  [Procurando botoes + das lojas...]")
        icones_mais = driver.find_elements(By.XPATH,
            "//li[contains(., 'H')]//button[contains(@class, 'add') or contains(@class, 'plus')] | "
            + "//tr[contains(., 'H')]//i[contains(@class, 'plus') or contains(@class, 'add')] | "
            + "//span[contains(text(), 'H')]/ancestor::li//button | "
            + "//span[contains(text(), 'H')]/preceding-sibling::button | "
            + "//button[contains(@class, 'rct-collapse-btn')]"
        )
        if icones_mais:
            print(f"  Encontrados {len(icones_mais)} icones + de lojas")
            for icone in icones_mais:
                try:
                    if icone.is_displayed():
                        driver.execute_script("arguments[0].click();", icone)
                        time.sleep(0.2)
                except:
                    pass
            print("  OK: Lojas adicionadas via icone +")
            return True
        
        checkboxes = driver.find_elements(By.XPATH,
            "//li[contains(., 'H')]//input[@type='checkbox'] | "
            + "//tr[contains(., 'H')]//input[@type='checkbox'] | "
            + "//span[contains(text(), 'H')]/preceding::input[@type='checkbox'][1] | "
            + "//label[contains(., 'H')]//input[@type='checkbox']"
        )
        if checkboxes:
            print(f"  Encontrados {len(checkboxes)} checkboxes de lojas")
            selecionados = 0
            for cb in checkboxes:
                try:
                    if cb.is_displayed() and not cb.is_selected():
                        driver.execute_script("arguments[0].click();", cb)
                        selecionados += 1
                        time.sleep(0.1)
                except:
                    pass
            print(f"  OK: {selecionados} lojas selecionadas via checkbox")
            return True
        
        resultado = driver.execute_script(
            "var todos = document.querySelectorAll('span, div, td, label');"
            + "var clicados = 0;"
            + "for (var i = 0; i < todos.length; i++) {"
            + "    var txt = todos[i].textContent || '';"
            + "    if (txt.match(/H\\d{3}/)) {"
            + "        var parent = todos[i].closest('li, tr, div');"
            + "        if (parent) {"
            + "            var btn = parent.querySelector('button, .rct-collapse-btn, i[class*=plus], i[class*=add], [class*=expand]');"
            + "            if (btn) {"
            + "                btn.click();"
            + "                clicados++;"
            + "            } else {"
            + "                var cb = parent.querySelector('input[type=checkbox]');"
            + "                if (cb && !cb.checked) {"
            + "                    cb.click();"
                    + "                    clicados++;"
            + "                }"
            + "            }"
            + "        }"
            + "    }"
            + "}"
            + "return 'Clicados: ' + clicados;"
        )
        print(f"  OK: {resultado}")
        return True
    except Exception as e:
        print(f"  AVISO ao selecionar lojas: {e}")
        return False

# ============================================================================
#  BAIXAR RELATORIO ESTOQUE DO CIGAM WEB
# ============================================================================
def baixar_estoque_cigam():
    print("=" * 70)
    print(" BAIXANDO RELATORIO DE ESTOQUE DO CIGAM WEB".center(70))
    print("=" * 70)

    arquivos_antigos = glob.glob(os.path.join(PASTA_DOWNLOADS_PADRAO, "*.xlsx"))
    for f in arquivos_antigos:
        try:
            os.remove(f)
        except:
            pass

    opcoes = Options()
    opcoes.add_argument("--start-maximized")
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--disable-blink-features=AutomationControlled")
    opcoes.add_experimental_option("excludeSwitches", ["enable-automation"])

    prefs = {
        "download.default_directory": PASTA_DOWNLOADS_PADRAO,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    opcoes.add_experimental_option("prefs", prefs)

    navegador = webdriver.Chrome(options=opcoes)
    aguardar = WebDriverWait(navegador, 20)

    try:
        print("\n[Acessando CIGAM...]")
        navegador.get("https://app.cigamgestor.com.br/login")
        time.sleep(3)

        aguardar.until(EC.presence_of_element_located((By.ID, "accesskey"))).send_keys(CIGAM_ACESSO)
        navegador.find_element(By.ID, "user").send_keys(CIGAM_USER)
        navegador.find_element(By.ID, "password").send_keys(CIGAM_SENHA)
        clique_forcado(navegador, "//*[@id='buttonLogin']", "botao login")
        time.sleep(5)
        print("Login realizado com sucesso!")

        print("\n[Navegando para pagina de relatorios...]")
        navegador.get("https://app.cigamgestor.com.br/relatorios/filtro")
        time.sleep(5)
        print("  OK: Pagina de relatorios carregada")

        print("\n[Aguardando arvore de relatorios carregar...]")
        arvore_carregada = False
        for i in range(20):
            time.sleep(1)
            try:
                arvore = navegador.find_elements(By.XPATH, "//span[contains(@class, 'rct-title')]")
                if arvore and len(arvore) > 5:
                    print(f"  OK: Arvore carregada com {len(arvore)} itens")
                    arvore_carregada = True
                    break
            except:
                pass
            try:
                body_text = navegador.find_element(By.TAG_NAME, "body").text
                if "Relatorios" in body_text or "Relatorios" in body_text:
                    if i > 5:
                        print(f"  OK: Pagina de relatorios detectada (tentativa {i})")
                        arvore_carregada = True
                        break
            except:
                pass
        
        if not arvore_carregada:
            print("  AVISO: Arvore nao detectada apos 20s, tentando continuar...")

        print("\n[Expandindo 6. Estoque...]")
        expandiu_estoque = False
        
        for tentativa in range(3):
            expandiu_estoque = tentar_clicar_multiplo(navegador, [
                "//span[contains(text(), '6. Estoque')]/ancestor::li[contains(@class, 'rct-node')]//button[contains(@class, 'rct-collapse-btn')]",
                "//span[contains(text(), '6. Estoque')]/preceding::button[contains(@class, 'rct-collapse')][1]",
                "//span[contains(text(), '6. Estoque')]/ancestor::span[contains(@class, 'rct-text')]//button",
                "//li[contains(., '6. Estoque')]//button[contains(@class, 'rct-collapse')]",
                "//span[contains(@class, 'rct-title') and contains(text(), '6. Estoque')]/ancestor::li//button[contains(@class, 'rct-collapse')]",
            ], f"expandir 6. Estoque (tentativa {tentativa + 1})")
            
            if expandiu_estoque:
                break
            time.sleep(2)
        
        if not expandiu_estoque:
            print("Tentando expandir via JS...")
            try:
                navegador.execute_script(
                    "var spans = document.querySelectorAll('span.rct-title');"
                    "for (var i = 0; i < spans.length; i++) {"
                    "    if (spans[i].textContent.includes('6. Estoque')) {"
                    "        var li = spans[i].closest('li');"
                    "        if (li) {"
                    "            var btn = li.querySelector('button.rct-collapse-btn');"
                    "            if (btn) { btn.click(); return 'Botao clicado'; }"
                    "            var icon = li.querySelector('.rct-node-icon, .rct-collapse, [class*=expand]');"
                    "            if (icon) { icon.click(); return 'Icone clicado'; }"
                    "        }"
                    "    }"
                    "}"
                    "return 'Nao encontrado';"
                )
                print("  OK: Expandido via JS")
                expandiu_estoque = True
            except Exception as e:
                print(f"  JS falhou: {e}")

        if not expandiu_estoque:
            print("  AVISO: Nao conseguiu expandir 6. Estoque, tentando continuar...")
        time.sleep(3)

        print("\n[Clicando em 6.1. Estoque Atual...]")
        estoque_atual_ok = False
        
        for tentativa in range(3):
            estoque_atual_ok = tentar_clicar_multiplo(navegador, [
                "//span[contains(@class, 'rct-title') and contains(text(), '6.1. Estoque Atual')]",
                "//span[contains(text(), '6.1. Estoque Atual')]",
                "//span[contains(text(), 'Estoque Atual') and contains(@class, 'rct-title')]",
                "//li[contains(., '6.1. Estoque Atual')]//span[contains(@class, 'rct-title')]",
                "//li[contains(@class, 'rct-node-leaf')]//span[contains(text(), 'Estoque Atual')]",
            ], f"6.1. Estoque Atual (tentativa {tentativa + 1})")
            
            if estoque_atual_ok:
                break
            time.sleep(2)
        
        if not estoque_atual_ok:
            estoque_atual_ok = scan_e_clicar(navegador, "6.1. Estoque Atual", "span")
        if not estoque_atual_ok:
            estoque_atual_ok = scan_e_clicar(navegador, "Estoque Atual", "span")
        
        if not estoque_atual_ok:
            print("Tentando via JS...")
            try:
                navegador.execute_script(
                    "var spans = document.querySelectorAll('span.rct-title');"
                    "for (var i = 0; i < spans.length; i++) {"
                    "    if (spans[i].textContent.includes('6.1.') && spans[i].textContent.includes('Estoque Atual')) {"
                    "        spans[i].click();"
                    "        return 'Clicado: ' + spans[i].textContent;"
                    "    }"
                    "}"
                    "for (var i = 0; i < spans.length; i++) {"
                    "    if (spans[i].textContent.includes('Estoque Atual')) {"
                    "        spans[i].click();"
                    "        return 'Clicado alternativo: ' + spans[i].textContent;"
                    "    }"
                    "}"
                    "return 'Nao encontrado';"
                )
                print("  OK: Clicado via JS")
                estoque_atual_ok = True
            except Exception as e:
                print(f"  JS falhou: {e}")

        if not estoque_atual_ok:
            raise Exception("NAO CONSEGUIU CLICAR EM 6.1. ESTOQUE ATUAL")
        time.sleep(5)

        print("\n[Clicando na aba Categoria...]")
        categoria_aba_ok = clicar_elemento_por_texto(navegador, "Categoria", max_tentativas=5)
        
        if not categoria_aba_ok:
            print("  AVISO: Nao conseguiu clicar em Categoria, tentando continuar...")
        time.sleep(3)

        print("\n[Expandindo e selecionando Acessorios...]")
        acessorios_ok = expandir_e_selecionar_item_arvore(navegador, "ACESSORIOS")
        
        if not acessorios_ok:
            for tentativa in range(3):
                acessorios_ok = tentar_clicar_multiplo(navegador, [
                    "//td[contains(text(), 'ACESSORIOS')]/preceding-sibling::td//input[@type='checkbox']",
                    "//td[contains(text(), 'ACESSORIOS')]/preceding-sibling::td//span[contains(@class, 'rct-checkbox')]",
                    "//tr[contains(., 'ACESSORIOS')]//input[@type='checkbox']",
                    "//tr[contains(., 'ACESSORIOS')]//span[contains(@class, 'checkbox')]",
                    "//span[contains(text(), 'ACESSORIOS')]/preceding::span[contains(@class, 'checkbox')][1]",
                    "//td[contains(text(), 'ACESSORIOS')]/ancestor::tr//input[@type='checkbox']",
                    "//label[contains(text(), 'ACESSORIOS')]//input[@type='checkbox']",
                ], f"checkbox Acessorios (tentativa {tentativa + 1})")
                
                if acessorios_ok:
                    break
                time.sleep(2)
        
        if not acessorios_ok:
            print("  AVISO: Nao conseguiu marcar Acessorios, pode ja estar selecionado")
        time.sleep(2)

        print("\n[Selecionando todas as lojas...]")
        loja_aba_ok = clicar_elemento_por_texto(navegador, "Loja", max_tentativas=5)
        
        if loja_aba_ok:
            time.sleep(3)
            selecionar_todas_lojas(navegador)
        else:
            print("  AVISO: Nao conseguiu clicar na aba Loja")

        time.sleep(2)

        print("\n[Voltando para aba Categoria...]")
        clicar_elemento_por_texto(navegador, "Categoria", max_tentativas=3)
        time.sleep(2)

        print("\n[Clicando em Visualizar...]")
        visualizou = False
        
        for tentativa in range(5):
            seletores_visualizar = [
                "//button[contains(text(), 'Visualizar')]",
                "//a[contains(text(), 'Visualizar')]",
                "//input[contains(@value, 'Visualizar')]",
                "//button[contains(@class, 'Visualizar')]",
                "//a[contains(@class, 'Visualizar')]",
                "//button[contains(text(), 'Visual')]",
                "//*[contains(text(), 'Visualizar') and (self::button or self::a or self::input)]",
                "//button[contains(@class, 'btn') and contains(text(), 'Visualizar')]",
                "//a[contains(@class, 'btn') and contains(text(), 'Visualizar')]",
                "//div[contains(@class, 'btn')]//a[contains(text(), 'Visualizar')]",
                "//span[contains(text(), 'Visualizar')]/parent::button",
                "//span[contains(text(), 'Visualizar')]/parent::a",
            ]
            
            for xpath in seletores_visualizar:
                try:
                    elementos = navegador.find_elements(By.XPATH, xpath)
                    for elem in elementos:
                        if elem.is_displayed():
                            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                            time.sleep(0.3)
                            navegador.execute_script("arguments[0].click();", elem)
                            print(f"  OK: Visualizar clicado (tentativa {tentativa + 1})")
                            visualizou = True
                            break
                    if visualizou:
                        break
                except:
                    continue
            if visualizou:
                break
            time.sleep(2)
        
        if not visualizou:
            print("Tentando encontrar botao Visualizar por scan em todos botoes...")
            try:
                botoes = navegador.find_elements(By.TAG_NAME, "button")
                for btn in botoes:
                    if 'VISUALIZAR' in btn.text.upper() or 'VISUAL' in btn.text.upper():
                        navegador.execute_script("arguments[0].click();", btn)
                        print(f"  OK: Botao Visualizar encontrado - '{btn.text}'")
                        visualizou = True
                        break
            except:
                pass
        
        if not visualizou:
            print("Tentando via JS querySelector em todos botoes e links...")
            try:
                resultado = navegador.execute_script(
                    "var botoes = document.querySelectorAll('button, a, input[type=button], input[type=submit]');"
                    "for (var i = 0; i < botoes.length; i++) {"
                    "    var txt = (botoes[i].textContent || botoes[i].value || botoes[i].innerText || '').toUpperCase();"
                    "    if (txt.includes('VISUALIZAR') || txt.includes('VISUAL')) {"
                    "        botoes[i].click();"
                    "        return 'Clicado: ' + txt;"
                    "    }"
                    "}"
                    "return 'Nao encontrado';"
                )
                if 'Clicado' in resultado:
                    print(f"  OK: Visualizar via JS - {resultado}")
                    visualizou = True
                else:
                    print(f"  JS: {resultado}")
            except Exception as e:
                print(f"  JS falhou: {e}")

        if not visualizou:
            raise Exception("NAO CONSEGUIU CLICAR EM VISUALIZAR")
        print("Aguardando relatorio carregar...")
        time.sleep(8)

        print("  Aguardando botao Salvar Arquivo...")
        for i in range(20):
            time.sleep(2)
            try:
                botoes = navegador.find_elements(By.XPATH, "//*[contains(text(), 'Salvar Arquivo')]")
                if botoes:
                    print("  OK: Relatorio carregado!")
                    break
            except:
                pass
        else:
            print("  AVISO: Timeout, tentando baixar mesmo assim...")

        print("\n[Baixando arquivo Excel...]")
        arquivos_antes = set(glob.glob(os.path.join(PASTA_DOWNLOADS_PADRAO, "*.xlsx")))

        xpaths_salvar = [
            "//button[contains(text(), 'Salvar Arquivo')]",
            "//a[contains(text(), 'Salvar Arquivo')]",
            "//input[contains(@value, 'Salvar Arquivo')]",
            "//*[contains(text(), 'Salvar Arquivo')]",
            "//button[contains(@class, 'salvar')]",
            "//a[contains(@class, 'salvar')]",
            "//button[contains(@class, 'download')]",
            "//a[contains(@class, 'download')]",
        ]

        clicou = False
        for xpath in xpaths_salvar:
            if clique_forcado(navegador, xpath, "Salvar Arquivo"):
                clicou = True
                break

        if not clicou:
            print("Tentando encontrar botao de download por scan...")
            try:
                todos_botoes = navegador.find_elements(By.TAG_NAME, "button")
                for btn in todos_botoes:
                    texto = btn.text.upper()
                    if 'SALVAR' in texto or 'DOWNLOAD' in texto or 'BAIXAR' in texto:
                        navegador.execute_script("arguments[0].click();", btn)
                        print(f"  OK: Botao encontrado por scan - '{btn.text}'")
                        clicou = True
                        break
            except:
                pass
        
        if not clicou:
            print("Tentando via JS...")
            try:
                navegador.execute_script(
                    "var botoes = document.querySelectorAll('button, a, input[type=button]');"
                    "for (var i = 0; i < botoes.length; i++) {"
                    "    var txt = (botoes[i].textContent || botoes[i].value || '').toUpperCase();"
                    "    if (txt.includes('SALVAR') || txt.includes('DOWNLOAD') || txt.includes('BAIXAR')) {"
                    "        botoes[i].click();"
                    "        return 'Clicado: ' + txt;"
                    "    }"
                    "}"
                    "return 'Nao encontrado';"
                )
                print("  OK: Download via JS")
                clicou = True
            except Exception as e:
                print(f"  JS falhou: {e}")

        if not clicou:
            raise Exception("NAO CONSEGUIU CLICAR EM SALVAR ARQUIVO")

        print("Aguardando download completar...")
        arquivo_baixado = None
        for i in range(30):
            time.sleep(2)
            arquivos_agora = set(glob.glob(os.path.join(PASTA_DOWNLOADS_PADRAO, "*.xlsx")))
            novos_arquivos = arquivos_agora - arquivos_antes

            if novos_arquivos:
                arquivo_baixado = max(novos_arquivos, key=os.path.getctime)
                try:
                    tamanho1 = os.path.getsize(arquivo_baixado)
                    time.sleep(1)
                    tamanho2 = os.path.getsize(arquivo_baixado)
                    if tamanho1 == tamanho2 and tamanho1 > 1000:
                        print(f"  OK: Download completo - {os.path.basename(arquivo_baixado)} ({tamanho1} bytes)")
                        break
                except:
                    pass

        if not arquivo_baixado:
            todos = glob.glob(os.path.join(PASTA_DOWNLOADS_PADRAO, "*.xlsx"))
            if todos:
                arquivo_baixado = max(todos, key=os.path.getctime)
                print(f"  AVISO: Usando arquivo mais recente: {os.path.basename(arquivo_baixado)}")
            else:
                raise Exception("Nenhum arquivo .xlsx encontrado!")

        caminho_destino = os.path.join(PASTA_DOWNLOAD_CIGAM, "Cigam.xlsx")
        if os.path.exists(caminho_destino):
            os.remove(caminho_destino)
        shutil.move(arquivo_baixado, caminho_destino)
        print(f"  OK: Arquivo movido para: {caminho_destino}")

        return caminho_destino

    except Exception as e:
        print(f"\nERRO durante download do CIGAM: {e}")
        traceback.print_exc()
        return None

    finally:
        if navegador:
            try:
                navegador.quit()
            except:
                pass
        print("Navegador fechado.")

# ============================================================================
#  PONTO DE ENTRADA
# ============================================================================
if __name__ == "__main__":
    verificar_licenca("ESTOQUE")
    
    caminho_cigam = baixar_estoque_cigam()
    
    if caminho_cigam:
        print("\n" + "=" * 70)
        print(" ESTOQUE BAIXADO COM SUCESSO ".center(70, "="))
        print(f" Arquivo: {caminho_cigam}")
        print("=" * 70)
    else:
        print("\nNao foi possivel baixar o relatorio do CIGAM.")
    
    os.system("pause")