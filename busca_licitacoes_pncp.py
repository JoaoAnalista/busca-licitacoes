#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script robusto para busca automática de licitações do estado do Paraná no PNCP
Desenvolvido para auxiliar analistas de licitação na busca diária de oportunidades
Versão com mecanismo de retry e endpoint alternativo para maior estabilidade
"""

import requests
import json
import datetime
import csv
import os
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# ============= CONFIGURAÇÕES (EDITE ESTA SEÇÃO) =============

# Pasta onde os resultados serão salvos
PASTA_RESULTADOS = "resultados_licitacoes"

# Configurações de email (obtidas de variáveis de ambiente)
import os
EMAIL_REMETENTE = os.environ.get("EMAIL_REMETENTE", "")
EMAIL_SENHA = os.environ.get("EMAIL_SENHA", "")
EMAIL_DESTINATARIO = os.environ.get("EMAIL_DESTINATARIO", "")

# Filtros para licitações
PALAVRAS_CHAVE = [
    "obra", "engenharia", "construção", "reforma", "pavimentação", 
    "edificação", "infraestrutura", "saneamento"
]

# Filtro para o estado do Paraná
# Códigos IBGE dos municípios do Paraná começam com 41
# CNPJ de órgãos municipais: primeiros 2 dígitos são 41
# Palavras-chave para identificar órgãos do Paraná
FILTRO_PARANA = [
    "paraná", "parana", "pr", 
    "curitiba", "londrina", "maringá", "maringa", "ponta grossa", 
    "cascavel", "são josé dos pinhais", "sao jose dos pinhais",
    "foz do iguaçu", "foz do iguacu", "colombo", "guarapuava"
]

# Configurações de retry
MAX_RETRIES = 5        # Número máximo de tentativas
RETRY_DELAY = 5        # Tempo de espera entre tentativas (segundos)
RETRY_BACKOFF = 2      # Fator de multiplicação do tempo de espera

# ============= FIM DAS CONFIGURAÇÕES =============

# Constantes do sistema
BASE_URL = "https://pncp.gov.br/api/consulta"
DATA_ATUAL = datetime.datetime.now().strftime("%Y-%m-%d")

def criar_pasta_resultados():
    """Cria a pasta para salvar os resultados se não existir"""
    if not os.path.exists(PASTA_RESULTADOS):
        os.makedirs(PASTA_RESULTADOS)
        print(f"Pasta de resultados criada: {PASTA_RESULTADOS}")

def fazer_requisicao_com_retry(url, params=None):
    """Faz uma requisição HTTP com mecanismo de retry para lidar com instabilidades"""
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=30)
            
            # Se a requisição for bem-sucedida, retorna a resposta
            if response.status_code == 200:
                return response
            
            # Se for um erro 400, tenta imprimir detalhes do erro
            if response.status_code == 400:
                print(f"Erro 400 (Bad Request) na tentativa {tentativa}/{MAX_RETRIES}")
                try:
                    erro_detalhes = response.json()
                    print(f"Detalhes do erro: {json.dumps(erro_detalhes, indent=2)}")
                except:
                    print(f"Resposta: {response.text}")
            
            # Para outros erros, apenas mostra o código
            else:
                print(f"Erro {response.status_code} na tentativa {tentativa}/{MAX_RETRIES}")
            
            # Se não for a última tentativa, espera antes de tentar novamente
            if tentativa < MAX_RETRIES:
                tempo_espera = RETRY_DELAY * (RETRY_BACKOFF ** (tentativa - 1))
                print(f"Aguardando {tempo_espera} segundos antes da próxima tentativa...")
                time.sleep(tempo_espera)
            
        except requests.exceptions.RequestException as e:
            print(f"Erro de conexão na tentativa {tentativa}/{MAX_RETRIES}: {e}")
            
            # Se não for a última tentativa, espera antes de tentar novamente
            if tentativa < MAX_RETRIES:
                tempo_espera = RETRY_DELAY * (RETRY_BACKOFF ** (tentativa - 1))
                print(f"Aguardando {tempo_espera} segundos antes da próxima tentativa...")
                time.sleep(tempo_espera)
    
    # Se todas as tentativas falharem, retorna None
    print(f"Todas as {MAX_RETRIES} tentativas falharam.")
    return None

def consultar_contratacoes_em_aberto():
    """Consulta contratações com recebimento de propostas em aberto no PNCP"""
    print("Consultando contratações com propostas em aberto...")
    
    endpoint = f"{BASE_URL}/v1/contratacoes/proposta"
    
    todas_contratacoes = []
    pagina_atual = 0
    total_paginas = 1  # Inicialização para entrar no loop
    
    # Loop para paginação
    while pagina_atual < total_paginas:
        params = {
            "pagina": pagina_atual,
            "tamanhoPagina": 100
        }
        
        response = fazer_requisicao_com_retry(endpoint, params)
        
        if response:
            try:
                dados = response.json()
                contratacoes = dados.get("data", [])
                todas_contratacoes.extend(contratacoes)
                
                # Atualiza informações de paginação
                total_paginas = dados.get("totalPaginas", 0)
                pagina_atual += 1
                
                print(f"Página {pagina_atual}/{total_paginas} processada. Encontradas {len(contratacoes)} contratações.")
            except Exception as e:
                print(f"Erro ao processar dados da API: {e}")
                break
        else:
            # Se a requisição falhar após todas as tentativas, interrompe o loop
            break
    
    print(f"Total de contratações encontradas: {len(todas_contratacoes)}")
    return todas_contratacoes

def consultar_contratacoes_recentes():
    """Tenta consultar contratações recentes usando diferentes endpoints"""
    print("Tentando consultar contratações usando diferentes métodos...")
    
    # Primeiro tenta o endpoint de propostas em aberto
    contratacoes = consultar_contratacoes_em_aberto()
    
    # Se não encontrar nada, tenta o endpoint de atualização
    if not contratacoes:
        print("Tentando endpoint alternativo de atualização...")
        endpoint = f"{BASE_URL}/v1/contratacoes/atualizacao"
        
        todas_contratacoes = []
        pagina_atual = 0
        total_paginas = 1
        
        while pagina_atual < total_paginas:
            params = {
                "pagina": pagina_atual,
                "tamanhoPagina": 100
            }
            
            response = fazer_requisicao_com_retry(endpoint, params)
            
            if response:
                try:
                    dados = response.json()
                    contratacoes = dados.get("data", [])
                    todas_contratacoes.extend(contratacoes)
                    
                    total_paginas = dados.get("totalPaginas", 0)
                    pagina_atual += 1
                    
                    print(f"Página {pagina_atual}/{total_paginas} processada. Encontradas {len(contratacoes)} contratações.")
                except Exception as e:
                    print(f"Erro ao processar dados da API: {e}")
                    break
            else:
                break
        
        contratacoes = todas_contratacoes
    
    print(f"Total de contratações encontradas em todos os métodos: {len(contratacoes)}")
    return contratacoes

def eh_do_parana(contratacao):
    """Verifica se a contratação é do estado do Paraná"""
    # Verifica CNPJ do órgão (se começa com 41 para municípios do PR)
    cnpj = contratacao.get("cnpjOrgao", "")
    if cnpj.startswith("41"):
        return True
    
    # Verifica nome do órgão
    razao_social = contratacao.get("razaoSocialOrgao", "").lower()
    
    # Verifica se contém "PR" como sigla do estado (com espaços/pontuação antes/depois para evitar falsos positivos)
    if " pr " in f" {razao_social} " or " pr," in f" {razao_social} " or " pr." in f" {razao_social} ":
        return True
    
    # Verifica se contém "paraná" ou variações
    if "parana" in razao_social or "paraná" in razao_social:
        return True
    
    # Verifica se contém nomes de cidades do Paraná
    for cidade in FILTRO_PARANA:
        if cidade in razao_social:
            return True
    
    # Verifica no objeto da licitação
    objeto = contratacao.get("objeto", "").lower()
    
    # Verifica se o objeto menciona Paraná ou cidades
    if "parana" in objeto or "paraná" in objeto:
        return True
    
    for cidade in FILTRO_PARANA:
        if cidade in objeto:
            return True
    
    # Se nenhuma condição for atendida, não é do Paraná
    return False

def filtrar_contratacoes_relevantes(contratacoes):
    """Filtra contratações relevantes (obras e serviços de engenharia do Paraná)"""
    print("Filtrando contratações relevantes do estado do Paraná...")
    
    relevantes = []
    
    for contratacao in contratacoes:
        # Verifica se é obra ou serviço de engenharia
        objeto = contratacao.get("objeto", "").lower()
        
        # Verifica se o objeto contém palavras-chave
        eh_relevante = any(palavra in objeto for palavra in PALAVRAS_CHAVE)
        
        # Verifica se é do Paraná
        do_parana = eh_do_parana(contratacao)
        
        # Se for relevante e do Paraná, adiciona à lista
        if eh_relevante and do_parana:
            relevantes.append(contratacao)
    
    print(f"Contratações relevantes do Paraná encontradas: {len(relevantes)}")
    return relevantes

def salvar_resultados_csv(contratacoes):
    """Salva os resultados em um arquivo CSV"""
    if not contratacoes:
        print("Nenhuma contratação relevante do Paraná encontrada para salvar.")
        return None
    
    # Cria pasta de resultados se não existir
    criar_pasta_resultados()
    
    # Nome do arquivo com data atual
    nome_arquivo = f"licitacoes_parana_{DATA_ATUAL}.csv"
    caminho_arquivo = os.path.join(PASTA_RESULTADOS, nome_arquivo)
    
    try:
        with open(caminho_arquivo, 'w', newline='', encoding='utf-8-sig') as arquivo:
            # Cria o escritor CSV
            escritor = csv.writer(arquivo)
            
            # Escreve o cabeçalho
            cabecalho = ["Número", "Órgão", "CNPJ", "Objeto", "Valor Estimado", 
                         "Data Publicação", "Data Abertura", "Modalidade", "URL"]
            escritor.writerow(cabecalho)
            
            # Escreve os dados
            for c in contratacoes:
                # Prepara a URL para acesso à licitação
                numero_controle = c.get("numeroControle", "")
                url = f"https://pncp.gov.br/contratacoes/{numero_controle.replace('/', '%2F')}"
                
                # Prepara os valores para o CSV
                linha = [
                    c.get("numeroControle", ""),
                    c.get("razaoSocialOrgao", ""),
                    c.get("cnpjOrgao", ""),
                    c.get("objeto", ""),
                    c.get("valorTotal", ""),
                    c.get("dataPublicacao", "").split("T")[0] if c.get("dataPublicacao") else "",
                    c.get("dataAbertura", "").split("T")[0] if c.get("dataAbertura") else "",
                    obter_nome_modalidade(c.get("modalidade", 0)),
                    url
                ]
                
                escritor.writerow(linha)
        
        print(f"Resultados salvos em: {caminho_arquivo}")
        return caminho_arquivo
        
    except Exception as e:
        print(f"Erro ao salvar arquivo CSV: {e}")
        return None

def obter_nome_modalidade(codigo_modalidade):
    """Converte o código da modalidade para o nome"""
    modalidades = {
        1: "Leilão - Eletrônico",
        2: "Diálogo Competitivo",
        3: "Concurso",
        4: "Concorrência - Eletrônica",
        5: "Concorrência - Presencial",
        6: "Pregão - Eletrônico",
        7: "Pregão - Presencial",
        8: "Dispensa de Licitação",
        9: "Inexigibilidade",
        10: "Manifestação de Interesse",
        11: "Pré-qualificação",
        12: "Credenciamento",
        13: "Leilão - Presencial"
    }
    
    return modalidades.get(codigo_modalidade, "Desconhecida")

def enviar_email_notificacao(arquivo_csv, total_licitacoes):
    """Envia email com notificação sobre as licitações encontradas"""
    # Verifica se as configurações de email foram fornecidas
    if not EMAIL_REMETENTE or not EMAIL_SENHA or not EMAIL_DESTINATARIO:
        print("Configurações de email não fornecidas. Notificação por email desativada.")
        return False
    
    # Verifica se o arquivo existe
    if not arquivo_csv or not os.path.exists(arquivo_csv):
        print("Arquivo CSV não encontrado. Email não enviado.")
        return False
    
    try:
        # Cria mensagem
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMETENTE
        msg['To'] = EMAIL_DESTINATARIO
        msg['Subject'] = f"Novas Licitações do Paraná - PNCP - {DATA_ATUAL}"
        
        # Corpo do email
        corpo = f"""
        <html>
        <body>
            <h2>Relatório Diário de Licitações do Paraná - PNCP</h2>
            <p>Olá,</p>
            <p>Foram encontradas <strong>{total_licitacoes}</strong> novas licitações relevantes do estado do Paraná no PNCP.</p>
            <p>Segue em anexo o arquivo CSV com os detalhes.</p>
            <p>Atenciosamente,<br>Sistema Automático de Monitoramento de Licitações</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(corpo, 'html'))
        
        # Anexa o arquivo CSV
        with open(arquivo_csv, 'rb') as file:
            part = MIMEApplication(file.read(), Name=os.path.basename(arquivo_csv))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(arquivo_csv)}"'
            msg.attach(part)
        
        # Envia o email
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(EMAIL_REMETENTE, EMAIL_SENHA)
        server.send_message(msg)
        server.quit()
        
        print("Email de notificação enviado com sucesso!")
        return True
        
    except Exception as e:
        print(f"Erro ao enviar email: {e}")
        return False

def verificar_status_pncp():
    """Verifica se o site do PNCP está acessível"""
    print("Verificando status do Portal Nacional de Contratações Públicas...")
    
    url = "https://pncp.gov.br"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print("Portal PNCP está online e acessível.")
            return True
        else:
            print(f"Portal PNCP retornou código de status: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Erro ao acessar o Portal PNCP: {e}")
        return False

def main():
    """Função principal do script"""
    print("=" * 60)
    print("BUSCA AUTOMÁTICA DE LICITAÇÕES DO PARANÁ NO PNCP")
    print("=" * 60)
    
    # Verifica status do PNCP
    pncp_online = verificar_status_pncp()
    
    if not pncp_online:
        print("AVISO: O Portal PNCP parece estar offline ou instável.")
        print("Tentando consultar mesmo assim...")
    
    # Consulta contratações usando diferentes métodos
    contratacoes = consultar_contratacoes_recentes()
    
    # Filtra contratações relevantes do Paraná
    relevantes = filtrar_contratacoes_relevantes(contratacoes)
    
    # Salva resultados
    arquivo_csv = salvar_resultados_csv(relevantes)
    
    # Envia notificação por email (se configurado)
    if arquivo_csv and len(relevantes) > 0:
        enviar_email_notificacao(arquivo_csv, len(relevantes))
    
    print("=" * 60)
    print("Busca concluída!")
    print("=" * 60)

if __name__ == "__main__":
    main()
