from __future__ import annotations

import io
import os
import re
import json
import time
import unicodedata
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

try:
    from geopy.geocoders import Nominatim
    _GEOPY_OK = True
except Exception:
    _GEOPY_OK = False

try:
    from pypdf import PdfReader
    _PYPDF_OK = True
except Exception:
    _PYPDF_OK = False

import folium
from streamlit_folium import st_folium


st.set_page_config(page_title="Extrator NF-e (Clientes)", page_icon="📄", layout="wide")

st.markdown("""
<style>
.main .block-container {max-width: 1280px; padding-top: 1.5rem;}
.stDownloadButton > button {border-radius: 10px; padding: 10px 16px; font-weight: 600;}

/* KPI cards */
.kpi-grid {display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px;}
.kpi {
    flex: 1; min-width: 140px;
    border-radius: 10px; padding: 16px 18px;
    background: #f8f9fb; border: 1px solid #eaecf0;
}
.kpi .label {color: #6b7280; font-size: 12px; margin-bottom: 4px;}
.kpi .value {font-weight: 700; font-size: 22px; color: #111827; line-height: 1.2;}
.kpi .sub {font-size: 11px; color: #9ca3af; margin-top: 3px;}
.kpi.green .value {color: #059669;}
.kpi.red .value {color: #dc2626;}
.kpi.blue .value {color: #2563eb;}
.kpi.orange .value {color: #d97706;}

/* Section header */
.section-header {
    display: flex; align-items: center; gap: 8px;
    font-size: 14px; font-weight: 600; color: #374151;
    margin: 1.5rem 0 .75rem; padding-bottom: 8px;
    border-bottom: 1px solid #f3f4f6;
}

/* Badge */
.badge {
    display: inline-block; padding: 2px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 600;
}
.badge-capital {background: #dbeafe; color: #1d4ed8;}
.badge-rm      {background: #d1fae5; color: #065f46;}
.badge-interior{background: #f3f4f6; color: #4b5563;}
.badge-pos     {background: #d1fae5; color: #065f46;}
.badge-neg     {background: #fee2e2; color: #991b1b;}
.badge-zero    {background: #f3f4f6; color: #6b7280;}

.leaflet-control-attribution {font-size: 12px !important;}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# CONSTANTES / TABELAS
# ──────────────────────────────────────────────

CLIENTES = [
    "PLUMA ESPUMAS LTDA (TXT/PDF)",
    "NORSA REFRIGERANTES S.A (XML)",
]

GEOCACHE_FILE = "geocache_destinos.json"
PLOT_HEIGHT   = 520

CAPITAL_IBGE_PE = {"RECIFE"}
RMR_IBGE_PE = {
    "RECIFE","OLINDA","JABOATAO DOS GUARARAPES","PAULISTA",
    "CABO DE SANTO AGOSTINHO","IPOJUCA","CAMARAGIBE",
    "SAO LOURENCO DA MATA","ABREU E LIMA","IGARASSU",
    "ITAPISSUMA","ARACOIABA","MORENO","ILHA DE ITAMARACA",
    "FERNANDO DE NORONHA",
}

CAPITAL_IBGE_AL = {"MACEIO"}
RMM_MACEIO_IBGE = {
    "ATALAIA","BARRA DE SANTO ANTONIO","BARRA DE SAO MIGUEL","COQUEIRO SECO",
    "MACEIO","MARECHAL DEODORO","MESSIAS","MURICI","PARIPUEIRA","PILAR",
    "RIO LARGO","SANTA LUZIA DO NORTE","SATUBA",
}

FRETE_TABELA_NOVA = {
    "AL": {
        "Capital":    {"Atual":100.00,"Colchão":120.00,"Conj. Box Solteiro":160.00,"Conj. Box Casal / Queen":190.00,"Conj. Box King":230.00},
        "RM":         {"Atual":200.00,"Colchão":200.00,"Conj. Box Solteiro":240.00,"Conj. Box Casal / Queen":280.00,"Conj. Box King":320.00},
        "Interior I": {"Atual":200.00,"Colchão":249.00,"Conj. Box Solteiro":310.00,"Conj. Box Casal / Queen":370.00,"Conj. Box King":395.00},
    },
    "PE": {
        "Capital":  {"Atual":130.00,"Colchão":140.00,"Conj. Box Solteiro":180.00,"Conj. Box Casal / Queen":220.00,"Conj. Box King":270.00},
        "RM":       {"Atual":130.00,"Colchão":140.00,"Conj. Box Solteiro":180.00,"Conj. Box Casal / Queen":220.00,"Conj. Box King":270.00},
        "Interior": {"Atual":249.00,"Colchão":249.00,"Conj. Box Solteiro":310.00,"Conj. Box Casal / Queen":370.00,"Conj. Box King":395.00},
    },
}

FRETE_ANTIGO_PE_REGIOES = {
    "MATA NORTE":249.00,"MATA SUL":249.00,"AGRESTE CENTRAL":249.00,
    "AGRESTE MERIDIONAL":249.00,"AGRESTE SETENTRIONAL":249.00,
    "SERTAO DO MOXOTO":360.00,"SERTAO DO PAJEU":380.00,
    "SERTAO DE ITAPARICA":400.00,"SERTAO CENTRAL":440.00,
    "SERTAO DO ARARIPE":470.00,"SERTAO DO SAO FRANCISCO":490.00,
}

PE_REGIOES_IBGE = {
    "MATA NORTE":{"ALIANCA","BUENOS AIRES","CAMUTANGA","CARPINA","CHA DE ALEGRIA","CONDADO","FERREIROS","GLORIA DO GOITA","GOIANA","ITAMBE","ITAQUITINGA","LAGOA DO CARRO","LAGOA DO ITAENGA","MACAPARANA","NAZARE DA MATA","PAUDALHO","TIMBAUBA","TRACUNHAEM","VICENCIA"},
    "MATA SUL":{"AGUA PRETA","AMARAJI","BARREIROS","BELEM DE MARIA","CATENDE","CHA GRANDE","CORTES","ESCADA","GAMELEIRA","JAQUEIRA","JOAQUIM NABUCO","MARAIAL","PALMARES","POMBOS","PRIMAVERA","QUIPAPA","RIBEIRAO","RIO FORMOSO","SAO BENEDITO DO SUL","SAO JOSE DA COROA GRANDE","SIRINHAEM","TAMANDARE","VITORIA DE SANTO ANTAO","XEXEU"},
    "AGRESTE CENTRAL":{"AGRESTINA","ALAGOINHA","ALTINHO","BARRA DE GUABIRABA","BELO JARDIM","BEZERROS","BONITO","BREJO DA MADRE DE DEUS","CACHOEIRINHA","CAMOCIM DE SAO FELIX","CARUARU","CUPIRA","GRAVATA","IBIRAJUBA","JATAUBA","LAGOA DOS GATOS","PANELAS","PESQUEIRA","POCAO","RIACHO DAS ALMAS","SAIRE","SANHARO","SAO BENTO DO UNA","SAO CAETANO","SAO JOAQUIM DO MONTE","TACAIMBO"},
    "AGRESTE MERIDIONAL":{"AGUAS BELAS","ANGELIM","BOM CONSELHO","BREJAO","BUIQUE","CAETES","CALCADO","CANHOTINHO","CAPOEIRAS","CORRENTES","GARANHUNS","IATI","ITAIBA","JUCATI","JUPI","JUREMA","LAGOA DO OURO","LAJEDO","PALMEIRINA","PARANATAMA","PEDRA","SALOA","SAO JOAO","TEREZINHA","TUPANATINGA","VENTUROSA"},
    "AGRESTE SETENTRIONAL":{"BOM JARDIM","CASINHAS","CUMARU","FEIRA NOVA","FREI MIGUELINHO","JOAO ALFREDO","LIMOEIRO","MACHADOS","OROBO","PASSIRA","SALGADINHO","SANTA CRUZ DO CAPIBARIBE","SANTA MARIA DO CAMBUCA","SAO VICENTE FERRER","SURUBIM","TAQUARITINGA DO NORTE","TORITAMA","VERTENTE DO LERIO","VERTENTES"},
    "SERTAO DO ARARIPE":{"ARARIPINA","BODOCO","EXU","GRANITO","IPUBI","MOREILANDIA","OURICURI","SANTA CRUZ","SANTA FILOMENA","TRINDADE"},
    "SERTAO CENTRAL":{"CEDRO","MIRANDIBA","PARNAMIRIM","SALGUEIRO","SAO JOSE DO BELMONTE","SERRITA","TERRA NOVA","VERDEJANTE"},
    "SERTAO DE ITAPARICA":{"BELEM DE SAO FRANCISCO","CARNAUBEIRA DA PENHA","FLORESTA","ITACURUBA","JATOBA","PETROLANDIA","TACARATU"},
    "SERTAO DO MOXOTO":{"ARCOVERDE","BETANIA","CUSTODIA","IBIMIRIM","INAJA","MANARI","SERTANIA"},
    "SERTAO DO PAJEU":{"AFOGADOS DA INGAZEIRA","BREJINHO","CALUMBI","CARNAIBA","FLORES","IGUARACI","INGAZEIRA","ITAPETIM","QUIXABA","SANTA CRUZ DA BAIXA VERDE","SANTA TEREZINHA","SAO JOSE DO EGITO","SERRA TALHADA","SOLIDAO","TABIRA","TRIUNFO","TUPARETAMA"},
    "SERTAO DO SAO FRANCISCO":{"AFRANIO","CABROBO","DORMENTES","LAGOA GRANDE","OROCO","PETROLINA","SANTA MARIA DA BOA VISTA"},
}

PE_MUNICIPIO_ALIASES = {
    "CABO DO STO. AGOSTINHO":"CABO DE SANTO AGOSTINHO",
    "CABO DO STO AGOSTINHO":"CABO DE SANTO AGOSTINHO",
    "CABO DE STO AGOSTINHO":"CABO DE SANTO AGOSTINHO",
    "JABOATAO DOSGUARARAPES":"JABOATAO DOS GUARARAPES",
    "ITAMARACA":"ILHA DE ITAMARACA",
    "BELEM DE S. FRANCISCO":"BELEM DE SAO FRANCISCO",
    "BELEM DE S FRANCISCO":"BELEM DE SAO FRANCISCO",
    "CAMAUBEIRA DA PENHA":"CARNAUBEIRA DA PENHA",
    "STA. CRUZ DA BAIXA VERDE":"SANTA CRUZ DA BAIXA VERDE",
    "STA CRUZ DA BAIXA VERDE":"SANTA CRUZ DA BAIXA VERDE",
    "STA. MARIA DO CAMBUCA":"SANTA MARIA DO CAMBUCA",
    "STA MARIA DO CAMBUCA":"SANTA MARIA DO CAMBUCA",
    "STA. CRUZ DO CAPIBARIBE":"SANTA CRUZ DO CAPIBARIBE",
    "STA CRUZ DO CAPIBARIBE":"SANTA CRUZ DO CAPIBARIBE",
    "TUPARATEMA":"TUPARETAMA",
}

NUM_BR  = r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)"
TEL_PAT = re.compile(r"(\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4}|\b\d{10,11}\b)")
RE_CEP_EXATO = re.compile(r"\b\d{5}-?\d{3}\b")


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def strip_accents_upper(s: str) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).upper().strip()

def sanitize_municipio_name(raw: str) -> str:
    if not raw: return ""
    s = str(raw).strip().split(",")[0]
    s = re.sub(r"\b(PE|PERNAMBUCO|AL|ALAGOAS)\b", "", s, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", s).strip()

def normalizar_municipio_pe(municipio: str) -> str:
    key = strip_accents_upper(sanitize_municipio_name(municipio))
    return PE_MUNICIPIO_ALIASES.get(key, key)

def obter_regiao_pe(municipio: str) -> Optional[str]:
    key = normalizar_municipio_pe(municipio)
    for regiao, municipios in PE_REGIOES_IBGE.items():
        if key in municipios:
            return regiao
    return None

def prox_nao_vazia(linhas, j, max_look=15):
    n, k, passos = len(linhas), j, 0
    while k < n and passos < max_look:
        val = (linhas[k] or "").strip()
        if val: return val
        k += 1; passos += 1
    return ""

def normalize_phone(raw: str) -> str:
    if not raw: return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11: return f"({digits[:2]}){digits[2:7]}-{digits[7:]}"
    if len(digits) == 10: return f"({digits[:2]}){digits[2:6]}-{digits[6:]}"
    return re.sub(r"\s+", " ", raw).strip()

def find_phone_in_text(txt: str) -> str:
    m = TEL_PAT.search(txt or "")
    return normalize_phone(m.group(1)) if m else ""

def extrair_cep_exato(txt: str) -> str:
    if not txt: return ""
    m = RE_CEP_EXATO.search(txt)
    if not m: return ""
    digits = re.sub(r"\D", "", m.group(0))
    return f"{digits[:5]}-{digits[5:]}" if len(digits) == 8 else m.group(0)

def detectar_origem_por_municipios(registros) -> str:
    municipios = []
    for reg in registros:
        mun = reg.get("MUNICÍPIO")
        if not mun: continue
        mun_clean = sanitize_municipio_name(mun)
        if mun_clean: municipios.append(strip_accents_upper(mun_clean))
    if not municipios: return "Recife (PE)"
    pe_hits = sum(1 for k in municipios if k in CAPITAL_IBGE_PE or k in RMR_IBGE_PE or obter_regiao_pe(k))
    al_hits = sum(1 for k in municipios if k in CAPITAL_IBGE_AL or k in RMM_MACEIO_IBGE)
    if al_hits > pe_hits or (al_hits > 0 and pe_hits == 0): return "Maceió (AL)"
    return "Recife (PE)"

def classificar_tipo_produto(descricao: str) -> str:
    d = strip_accents_upper(descricao or "")
    if d.startswith("COLCHAO"): return "Colchão"
    if "KING" in d or " 193 " in f" {d} ": return "Conj. Box King"
    if "SOLTEIRO" in d or " 88 " in f" {d} ": return "Conj. Box Solteiro"
    return "Conj. Box Casal / Queen"

def extrair_produto_servico_do_bloco(texto_nota: str) -> Dict[str, str]:
    inicio = texto_nota.find("DADOS DOS PRODUTOS")
    fim    = texto_nota.find("RESERVADO AO FISCO", inicio)
    if inicio == -1:
        return {"CÓDIGO PRODUTO":"","DESCRIÇÃO DO PRODUTO / SERVIÇO":"","QTDE PRODUTO":""}
    bloco = " ".join(texto_nota[inicio:fim if fim != -1 else None].split())
    m = re.search(r"(\d{4,6})\s+(.+?)\s+(\d{8})\s+\d{3,4}\s+\d{4}\s+\w+\s+([\d.,]+)\s+", bloco, flags=re.IGNORECASE)
    if not m:
        return {"CÓDIGO PRODUTO":"","DESCRIÇÃO DO PRODUTO / SERVIÇO":"","QTDE PRODUTO":""}
    return {"CÓDIGO PRODUTO":m.group(1),"DESCRIÇÃO DO PRODUTO / SERVIÇO":m.group(2).strip(),"QTDE PRODUTO":m.group(4)}

def classificar_regiao_nova(municipio: str, origem: str) -> Tuple[str, str]:
    key = normalizar_municipio_pe(municipio)
    origem_norm = strip_accents_upper(origem)
    if "MACEIO" in origem_norm:
        if key in CAPITAL_IBGE_AL: return "AL","Capital"
        if key in RMM_MACEIO_IBGE: return "AL","RM"
        return "AL","Interior I"
    if key in CAPITAL_IBGE_PE: return "PE","Capital"
    if key in RMR_IBGE_PE:     return "PE","RM"
    return "PE","Interior"

def calcular_frete_novo(municipio: str, origem: str, descricao: str) -> Tuple[str, str, float]:
    uf, regiao = classificar_regiao_nova(municipio, origem)
    tipo = classificar_tipo_produto(descricao)
    return regiao, tipo, FRETE_TABELA_NOVA[uf][regiao][tipo]

def calcular_frete_antigo(municipio: str, origem: str) -> Tuple[str, float]:
    key = normalizar_municipio_pe(municipio)
    origem_norm = strip_accents_upper(origem)
    if "MACEIO" in origem_norm:
        if key in CAPITAL_IBGE_AL: return "Capital",100.00
        if key in RMM_MACEIO_IBGE: return "RM",200.00
        return "Interior I",200.00
    if key in CAPITAL_IBGE_PE: return "Capital",130.00
    if key in RMR_IBGE_PE:     return "RM",130.00
    regiao_pe = obter_regiao_pe(key)
    if regiao_pe: return regiao_pe, FRETE_ANTIGO_PE_REGIOES[regiao_pe]
    return "Interior",249.00

def classificar_zona_para_mapa(municipio: str, origem: str):
    regiao, _, frete = calcular_frete_novo(municipio, origem, "")
    if regiao == "RM": return "Metropolitana", frete
    return regiao, frete

def extrair_texto_upload(uploaded) -> str:
    data = uploaded.read()
    name = uploaded.name.lower()
    if name.endswith(".pdf"):
        if not _PYPDF_OK:
            raise RuntimeError("Para ler PDF, instale pypdf: pip install pypdf")
        reader = PdfReader(BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8", errors="ignore")

def split_notas_texto(texto: str) -> List[str]:
    # "Recebemos de" aparece no in?cio de cada DANFE e ? mais est?vel que
    # depender da frase inteira, que pode vir com acentua??o diferente no PDF.
    partes = re.split(r"(?=Recebemos\s+de\s+)", texto, flags=re.IGNORECASE)
    partes = [p.strip() for p in partes if p.strip()]
    return partes if len(partes) > 1 else [texto]

def extrair_campo_por_label(linhas: List[str], label_regex: str, max_look=15) -> str:
    for i, linha in enumerate(linhas):
        if re.fullmatch(label_regex, linha, flags=re.IGNORECASE):
            return prox_nao_vazia(linhas, i + 1, max_look=max_look)
    return ""

def extrair_nota_unica(texto_nota: str) -> Optional[Dict[str, Any]]:
    linhas     = [l.strip() for l in texto_nota.splitlines()]
    texto_join = "\n".join(linhas)
    m_num = (
        re.search(r"NF-e\s*N[ºo]?\s*([0-9.\-]+)", texto_join, flags=re.IGNORECASE)
        or re.search(r"\bN[ºo]\s*([0-9.\-]+)", texto_join, flags=re.IGNORECASE)
    )
    if not m_num: return None

    reg = {
        "Nº": m_num.group(1),
        "NOME / RAZÃO SOCIAL":"","ENDEREÇO":"","BAIRRO / DISTRITO":"","MUNICÍPIO":"",
        "CEP":"","VALOR TOTAL DA NOTA":"","QUANTIDADE":"","PESO BRUTO":"","CUBAGEM":"",
        "TELEFONE / FAX":"","TELEFONE 2":"","VENDEDOR":"","INTEGRACAO":"",
        "CÓDIGO PRODUTO":"","DESCRIÇÃO DO PRODUTO / SERVIÇO":"","QTDE PRODUTO":"",
    }

    reg["NOME / RAZÃO SOCIAL"] = extrair_campo_por_label(linhas, r"NOME\s*/\s*RAZÃO SOCIAL")
    reg["ENDEREÇO"]            = extrair_campo_por_label(linhas, r"ENDEREÇO")
    reg["BAIRRO / DISTRITO"]   = extrair_campo_por_label(linhas, r"BAIRRO\s*/\s*DISTRITO")
    reg["MUNICÍPIO"]           = extrair_campo_por_label(linhas, r"MUNICÍPIO")
    reg["CEP"]                 = extrair_cep_exato(extrair_campo_por_label(linhas, r"CEP")) or extrair_cep_exato(texto_join)

    if reg["MUNICÍPIO"]:
        reg["MUNICÍPIO"] = re.split(r"\bUF\b|CEP|\bPE\b|\bAL\b|\d{2}:\d{2}:\d{2}", reg["MUNICÍPIO"], maxsplit=1)[0].strip(" -")

    m_val = re.search(r"VALOR TOTAL DA NOTA\s*\n\s*" + NUM_BR, texto_join, flags=re.IGNORECASE)
    if m_val: reg["VALOR TOTAL DA NOTA"] = m_val.group(1)

    m_qt = re.search(r"(\d+)\s+VOLUMES", texto_join, flags=re.IGNORECASE)
    if m_qt: reg["QUANTIDADE"] = m_qt.group(1)

    m_peso = re.search(r"(\d+)\s+VOLUMES\s+\d+\s+" + NUM_BR + r"\s+" + NUM_BR, texto_join, flags=re.IGNORECASE)
    if m_peso:
        reg["PESO BRUTO"] = m_peso.group(2)
    else:
        m_peso2 = re.search(r"PESO\s+BRUTO\s*\n\s*" + NUM_BR, texto_join, flags=re.IGNORECASE)
        if m_peso2: reg["PESO BRUTO"] = m_peso2.group(1)

    m_fone_label = re.search(r"TELEFONE\s*/\s*FAX\s*\n\s*([^\n]+)", texto_join, flags=re.IGNORECASE)
    if m_fone_label and not re.search(r"INSCRIÇÃO|DESTINAT[ÁA]RIO", m_fone_label.group(1), flags=re.IGNORECASE):
        reg["TELEFONE / FAX"] = find_phone_in_text(m_fone_label.group(1))
    if not reg["TELEFONE / FAX"]:
        reg["TELEFONE / FAX"] = find_phone_in_text(texto_join)

    m_t2 = re.search(r"TELEFONE\s*2\s*:\s*([^;]*)", texto_join, flags=re.IGNORECASE)
    if m_t2: reg["TELEFONE 2"] = find_phone_in_text(m_t2.group(1))

    m_vend = re.search(r"#VENDEDOR\s*:\s*(.*?)\s+NOSSO\s+PEDIDO", texto_join, flags=re.IGNORECASE)
    if m_vend: reg["VENDEDOR"] = m_vend.group(1).strip(" :;-")

    m_int = re.search(r"Integracao\s*:\s*(.+?)(?:-+\s*EntregaID\b|;|\Z)", texto_join, flags=re.IGNORECASE | re.S)
    if m_int: reg["INTEGRACAO"] = " ".join(m_int.group(1).split()).strip(" :;-")

    m_cub = re.search(r"CUBAGEM\s*[:\-]\s*([^;]+)", texto_join, flags=re.IGNORECASE)
    if m_cub: reg["CUBAGEM"] = m_cub.group(1).strip()

    reg.update(extrair_produto_servico_do_bloco(texto_nota))
    return reg

def extrair_notas_de_texto(texto: str):
    registros = []
    for parte in split_notas_texto(texto):
        reg = extrair_nota_unica(parte)
        if reg: registros.append(reg)
    return registros

def salvar_excel_bytes_pluma(registros, origem: str) -> Tuple[bytes, pd.DataFrame]:
    df = pd.DataFrame(registros)
    zonas, tipos_frete, fretes_antigos, fretes_novos, diferencas = [], [], [], [], []
    for _, row in df.iterrows():
        descricao = row.get("DESCRIÇÃO DO PRODUTO / SERVIÇO", "")
        _, frete_antigo = calcular_frete_antigo(row.get("MUNICÍPIO", ""), origem)
        z, tipo, frete_novo = calcular_frete_novo(row.get("MUNICÍPIO", ""), origem, descricao)
        zonas.append(z); tipos_frete.append(tipo)
        fretes_antigos.append(frete_antigo); fretes_novos.append(frete_novo)
        diferencas.append(frete_novo - frete_antigo)
    df["ZONA"] = zonas
    df["TIPO FRETE"] = tipos_frete
    df["VALOR FRETE ANTIGO"] = fretes_antigos
    df["VALOR FRETE"] = fretes_novos
    df["DIFERENÇA FRETE"] = diferencas

    colunas = [
        "Nº","NOME / RAZÃO SOCIAL","ENDEREÇO","BAIRRO / DISTRITO","MUNICÍPIO","CEP",
        "VALOR TOTAL DA NOTA","CÓDIGO PRODUTO","DESCRIÇÃO DO PRODUTO / SERVIÇO","QTDE PRODUTO",
        "QUANTIDADE","PESO BRUTO","CUBAGEM","TELEFONE / FAX","TELEFONE 2","VENDEDOR","INTEGRACAO",
        "ZONA","TIPO FRETE","VALOR FRETE ANTIGO","VALOR FRETE","DIFERENÇA FRETE",
    ]
    df = df.reindex(columns=colunas)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Notas")
        workbook  = writer.book
        worksheet = writer.sheets["Notas"]
        money_fmt = workbook.add_format({"num_format": 'R$ #,##0.00'})
        for idx, col in enumerate(df.columns):
            width = max(12, min(55, max(len(str(col)), int(df[col].astype(str).str.len().quantile(0.95)) if len(df) else 12) + 2))
            worksheet.set_column(idx, idx, width)
            if col in {"VALOR FRETE ANTIGO","VALOR FRETE","DIFERENÇA FRETE"}:
                worksheet.set_column(idx, idx, 14, money_fmt)
    buffer.seek(0)
    return buffer.read(), df


# ──────────────────────────────────────────────
# GEOCODIFICAÇÃO / MAPA
# ──────────────────────────────────────────────

def load_geocache() -> dict:
    if os.path.exists(GEOCACHE_FILE):
        try:
            with open(GEOCACHE_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: return {}
    return {}

def save_geocache(cache: dict):
    try:
        with open(GEOCACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception: pass

COORDS_FALLBACK_RAW = {
    "RECIFE, PE":(-8.0476,-34.8770),"MACEIO, AL":(-9.6658,-35.7353),
    "RIO LARGO, AL":(-9.4783,-35.8533),"MARECHAL DEODORO, AL":(-9.7103,-35.8950),
    "PILAR, AL":(-9.6014,-35.9567),"SATUBA, AL":(-9.5694,-35.8244),
    "PARIPUEIRA, AL":(-9.4631,-35.5528),"SANTA LUZIA DO NORTE, AL":(-9.6036,-35.8236),
    "OLINDA, PE":(-8.0101,-34.8545),"JABOATAO DOS GUARARAPES, PE":(-8.1120,-35.0140),
    "PAULISTA, PE":(-7.9400,-34.8731),"CABO DE SANTO AGOSTINHO, PE":(-8.2822,-35.0320),
    "IPOJUCA, PE":(-8.3983,-35.0639),"CAMARAGIBE, PE":(-8.0207,-34.9786),
    "SAO LOURENCO DA MATA, PE":(-8.0062,-35.0199),"ABREU E LIMA, PE":(-7.9007,-34.9027),
    "IGARASSU, PE":(-7.8340,-34.9069),"ITAPISSUMA, PE":(-7.7750,-34.8954),
    "ARACOIABA, PE":(-7.7913,-35.0800),"MORENO, PE":(-8.1180,-35.0920),
    "ILHA DE ITAMARACA, PE":(-7.7478,-34.8332),
}
COORDS_FALLBACK_NORM = {strip_accents_upper(k): v for k, v in COORDS_FALLBACK_RAW.items()}

def geocode_city(city: str, uf: str) -> Optional[Tuple[float, float]]:
    city_clean = sanitize_municipio_name(city)
    key_raw  = f"{city_clean}, {uf}"
    key_norm = strip_accents_upper(key_raw)
    cache = st.session_state.get("geocache", {})
    if key_raw in cache and cache[key_raw]: return tuple(cache[key_raw])
    if key_norm in COORDS_FALLBACK_NORM:
        latlon = COORDS_FALLBACK_NORM[key_norm]
        cache[key_raw] = latlon; st.session_state["geocache"] = cache; save_geocache(cache)
        return latlon
    if _GEOPY_OK:
        try:
            estado_nome = "Alagoas" if uf == "AL" else "Pernambuco"
            geolocator  = Nominatim(user_agent="nf_extractor_ws")
            loc = geolocator.geocode(f"{city_clean}, {estado_nome}, Brazil", timeout=10)
            if loc:
                latlon = (loc.latitude, loc.longitude)
                cache[key_raw] = latlon; st.session_state["geocache"] = cache; save_geocache(cache)
                time.sleep(1.0); return latlon
        except Exception: pass
    cache[key_raw] = None; st.session_state["geocache"] = cache; save_geocache(cache)
    return None

def _color_for(z):
    if z == "Capital": return "red"
    if z in {"Metropolitana","RM"}: return "blue"
    return "gray"

def build_map_folium(df_destinos: pd.DataFrame, origem: str):
    if df_destinos.empty:
        st.info("Sem destinos válidos para plotar no mapa."); return
    origem_norm = strip_accents_upper(origem)
    center = [-9.6658,-35.7353] if "MACEIO" in origem_norm else [-8.0476,-34.8770]
    m = folium.Map(location=center, zoom_start=7, tiles="OpenStreetMap")
    lats, lons = [], []
    for _, row in df_destinos.iterrows():
        lat, lon = row["lat"], row["lon"]
        qtd = int(row.get("QTD_ENTREGAS", 1))
        lats.append(lat); lons.append(lon)
        cor = _color_for(row["ZONA"])
        html_marker = f"""<div style="background:{cor};color:white;border:2px solid white;border-radius:50%;
            width:30px;height:30px;line-height:26px;text-align:center;font-size:12px;font-weight:700;
            box-shadow:0 0 4px rgba(0,0,0,0.35);">{qtd}</div>"""
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(html=html_marker),
            popup=folium.Popup(html=f"<b>{row['municipio']}</b><br/>Zona: {row['ZONA']}<br/>Entregas: {qtd}", max_width=260),
            tooltip=f"{row['municipio']} • {row['ZONA']} • {qtd} entrega(s)",
        ).add_to(m)
    if lats and lons: m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    m.get_root().html.add_child(folium.Element("""
    <div style="position:fixed;bottom:20px;left:20px;z-index:9999;background:rgba(255,255,255,0.98);
        padding:10px 12px;border:1px solid #bbb;border-radius:8px;color:#111;font-size:13px;">
      <div style="font-weight:700;margin-bottom:6px;">Legenda</div>
      <div><span style="background:red;width:12px;height:12px;display:inline-block;border-radius:50%;margin-right:6px;"></span>Capital</div>
      <div><span style="background:blue;width:12px;height:12px;display:inline-block;border-radius:50%;margin-right:6px;"></span>RM</div>
      <div><span style="background:gray;width:12px;height:12px;display:inline-block;border-radius:50%;margin-right:6px;"></span>Interior</div>
    </div>"""))
    st_folium(m, width=None, height=PLOT_HEIGHT)


# ──────────────────────────────────────────────
# NORSA — XML
# ──────────────────────────────────────────────

def _detect_ns(root: ET.Element) -> Dict[str, str]:
    m = re.match(r"\{(.+)\}", root.tag or "")
    return {"nfe": m.group(1)} if m else {"nfe": ""}

def _find_text(parent, xpath, ns):
    if parent is None: return None
    el = parent.find(xpath, ns) if ns.get("nfe") else parent.find(xpath.replace("nfe:", ""))
    if el is not None and el.text:
        t = el.text.strip()
        return t if t else None
    return None

def _find_first_text(parent, xpaths, ns):
    for xp in xpaths:
        v = _find_text(parent, xp, ns)
        if v is not None: return v
    return None

def _to_float(s):
    if s is None: return None
    try: return float(s)
    except Exception: return None

def parse_nfe_xml(xml_bytes: bytes) -> Dict[str, Any]:
    root = ET.fromstring(xml_bytes)
    ns   = _detect_ns(root)
    inf  = root.find(".//nfe:infNFe", ns) if ns.get("nfe") else root.find(".//infNFe")
    if inf is None: raise ValueError("Não encontrei <infNFe> no XML.")
    numero = _find_text(inf, "./nfe:ide/nfe:nNF", ns)
    nome   = _find_text(inf, "./nfe:dest/nfe:xNome", ns)
    xLgr   = _find_text(inf, "./nfe:dest/nfe:enderDest/nfe:xLgr", ns)
    nro    = _find_text(inf, "./nfe:dest/nfe:enderDest/nfe:nro", ns)
    xCpl   = _find_text(inf, "./nfe:dest/nfe:enderDest/nfe:xCpl", ns)
    endereco_parts = [p for p in [xLgr, nro] if p]
    endereco = ", ".join(endereco_parts) if endereco_parts else None
    if xCpl: endereco = f"{endereco} - {xCpl}" if endereco else xCpl
    dets  = inf.findall("./nfe:det", ns) if ns.get("nfe") else inf.findall("./det")
    prod0 = dets[0].find("./nfe:prod", ns) if dets and ns.get("nfe") else (dets[0].find("./prod") if dets else None)
    return {
        "Nº": numero,
        "NOME / RAZÃO SOCIAL": nome,
        "ENDEREÇO": endereco,
        "BAIRRO / DISTRITO": _find_text(inf, "./nfe:dest/nfe:enderDest/nfe:xBairro", ns),
        "MUNICÍPIO": _find_text(inf, "./nfe:dest/nfe:enderDest/nfe:xMun", ns),
        "CEP": _find_text(inf, "./nfe:dest/nfe:enderDest/nfe:CEP", ns),
        "V. TOTAL DA NOTA": _to_float(_find_text(inf, "./nfe:total/nfe:ICMSTot/nfe:vNF", ns)),
        "CÓDIGO PRODUTO": _find_text(prod0, "./nfe:cProd", ns) if prod0 is not None else None,
        "DESCRIÇÃO DO PRODUTO / SERVIÇO": _find_text(prod0, "./nfe:xProd", ns) if prod0 is not None else None,
        "QTDE PRODUTO": _to_float(_find_text(prod0, "./nfe:qCom", ns)) if prod0 is not None else None,
        "QUANTIDADE": _to_float(_find_text(inf, "./nfe:transp/nfe:vol/nfe:qVol", ns)),
        "PESO BRUTO": _to_float(_find_first_text(inf, ["./nfe:transp/nfe:vol/nfe:pesoB","./nfe:transp/nfe:vol/nfe:pBruto"], ns)),
        "TELEFONE / FAX": _find_first_text(inf, ["./nfe:dest/nfe:enderDest/nfe:fone","./nfe:emit/nfe:enderEmit/nfe:fone"], ns),
    }

def salvar_excel_bytes_norsa(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="NFes")
    output.seek(0)
    return output.read()


# ──────────────────────────────────────────────
# FUNÇÕES DO DASHBOARD (NOVO)
# ──────────────────────────────────────────────

ZONA_COLORS  = {"Capital":"#2563eb","RM":"#059669","Interior":"#6b7280","Interior I":"#9ca3af"}
TIPO_COLORS  = {"Colchão":"#7c3aed","Conj. Box Solteiro":"#d97706","Conj. Box Casal / Queen":"#0891b2","Conj. Box King":"#dc2626"}

def moeda_br(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",","X").replace(".",",").replace("X",".")

def render_kpi(label, value, sub="", color_class=""):
    cor_map = {"green":"#059669","red":"#dc2626","blue":"#2563eb","orange":"#d97706","":"#111827"}
    cor = cor_map.get(color_class, "#111827")
    st.markdown(f"""
    <div class="kpi">
        <div class="label">{label}</div>
        <div class="value" style="color:{cor}">{value}</div>
        {"<div class='sub'>"+sub+"</div>" if sub else ""}
    </div>""", unsafe_allow_html=True)

def dashboard_pluma(df: pd.DataFrame, origem: str):
    # ── KPIs ──────────────────────────────────────
    capital_c = int((df["ZONA"] == "Capital").sum())
    rm_c      = int((df["ZONA"] == "RM").sum())
    int_c     = int((~df["ZONA"].isin(["Capital","RM"])).sum())
    total_ant = float(df["VALOR FRETE ANTIGO"].fillna(0).sum())
    total_nov = float(df["VALOR FRETE"].fillna(0).sum())
    dif_tot   = float(df["DIFERENÇA FRETE"].fillna(0).sum())
    notas_com_alta = int((df["DIFERENÇA FRETE"] > 0).sum())

    st.markdown('<div class="section-header">📊 Resumo geral</div>', unsafe_allow_html=True)
    c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
    kpis = [
        (c1, "Notas extraídas",         str(len(df)),              "total processado",          ""),
        (c2, "Municípios distintos",     str(df["MUNICÍPIO"].nunique()), "destinos únicos",       "blue"),
        (c3, "Capital / RM / Interior",  f"{capital_c}/{rm_c}/{int_c}", "distribuição de zonas", ""),
        (c4, "Frete antigo total",       moeda_br(total_ant),       "tabela antiga",             ""),
        (c5, "Frete novo total",         moeda_br(total_nov),       "tabela nova",               "green"),
        (c6, "Diferença total",          moeda_br(dif_tot),         "impacto da mudança",        "red" if dif_tot > 0 else "green"),
        (c7, "Notas com alta",           str(notas_com_alta),       "tiveram reajuste",          "orange" if notas_com_alta > 0 else ""),
    ]
    for col, label, value, sub, cls in kpis:
        with col:
            render_kpi(label, value, sub, cls)

    st.markdown("")

    # ── LINHA 1: Pizza zonas + Rosca tipos ────────
    st.markdown('<div class="section-header">🗂️ Distribuição das notas</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)

    with col_a:
        zona_counts = df["ZONA"].value_counts()
        fig_zona = go.Figure(go.Pie(
            labels=zona_counts.index.tolist(),
            values=zona_counts.values.tolist(),
            hole=0,
            marker_colors=[ZONA_COLORS.get(z,"#6b7280") for z in zona_counts.index],
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>%{value} notas (%{percent})<extra></extra>",
        ))
        fig_zona.update_layout(
            title="Notas por zona",
            showlegend=False,
            margin=dict(t=40,b=10,l=10,r=10),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_zona, use_container_width=True)

    with col_b:
        tipo_counts = df["TIPO FRETE"].value_counts()
        fig_tipo = go.Figure(go.Pie(
            labels=tipo_counts.index.tolist(),
            values=tipo_counts.values.tolist(),
            hole=0.45,
            marker_colors=[TIPO_COLORS.get(t,"#6b7280") for t in tipo_counts.index],
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>%{value} notas (%{percent})<extra></extra>",
        ))
        fig_tipo.update_layout(
            title="Notas por tipo de produto",
            showlegend=False,
            margin=dict(t=40,b=10,l=10,r=10),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_tipo, use_container_width=True)

    # ── LINHA 2: Comparativo frete por segmento ───
    st.markdown('<div class="section-header">💰 Comparativo de frete: antigo vs novo</div>', unsafe_allow_html=True)

    resumo_seg = (
        df.groupby(["ZONA","TIPO FRETE"], dropna=False)
        .agg(TOTAL_ANTIGO=("VALOR FRETE ANTIGO","sum"), TOTAL_NOVO=("VALOR FRETE","sum"), QTD=("Nº","count"))
        .reset_index()
        .sort_values(["ZONA","TIPO FRETE"])
    )
    resumo_seg["SEGMENTO"] = resumo_seg["ZONA"] + " / " + resumo_seg["TIPO FRETE"]
    resumo_seg["DIFERENÇA"] = resumo_seg["TOTAL_NOVO"] - resumo_seg["TOTAL_ANTIGO"]

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(
        name="Frete antigo", x=resumo_seg["SEGMENTO"], y=resumo_seg["TOTAL_ANTIGO"],
        marker_color="#93c5fd", marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Antigo: R$ %{y:,.2f}<extra></extra>",
    ))
    fig_comp.add_trace(go.Bar(
        name="Frete novo", x=resumo_seg["SEGMENTO"], y=resumo_seg["TOTAL_NOVO"],
        marker_color="#059669", marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Novo: R$ %{y:,.2f}<extra></extra>",
    ))
    fig_comp.update_layout(
        barmode="group",
        title="Total frete antigo vs novo por zona × tipo",
        xaxis_tickangle=-30,
        xaxis=dict(tickfont=dict(size=11)),
        yaxis=dict(tickprefix="R$ ", tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=50,b=80,l=60,r=20),
        height=380,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig_comp.update_xaxes(showgrid=False)
    fig_comp.update_yaxes(gridcolor="rgba(0,0,0,0.07)")
    st.plotly_chart(fig_comp, use_container_width=True)

    # ── LINHA 3: Variação por zona (barras) + diferença por segmento ──
    col_c, col_d = st.columns(2)

    with col_c:
        resumo_zona = (
            df.groupby("ZONA", dropna=False)
            .agg(TOTAL_ANTIGO=("VALOR FRETE ANTIGO","sum"), TOTAL_NOVO=("VALOR FRETE","sum"), QTD=("Nº","count"))
            .reset_index()
        )
        resumo_zona["DIFERENÇA"] = resumo_zona["TOTAL_NOVO"] - resumo_zona["TOTAL_ANTIGO"]
        cores_zona = [ZONA_COLORS.get(z,"#6b7280") for z in resumo_zona["ZONA"]]

        fig_var = go.Figure(go.Bar(
            x=resumo_zona["ZONA"],
            y=resumo_zona["DIFERENÇA"],
            marker_color=cores_zona,
            marker_line_width=0,
            text=[moeda_br(v) for v in resumo_zona["DIFERENÇA"]],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Variação: R$ %{y:,.2f}<extra></extra>",
        ))
        fig_var.update_layout(
            title="Variação total de frete por zona",
            yaxis=dict(tickprefix="R$ ", tickfont=dict(size=11)),
            xaxis=dict(tickfont=dict(size=12)),
            margin=dict(t=40,b=20,l=60,r=20),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_var.update_xaxes(showgrid=False)
        fig_var.update_yaxes(gridcolor="rgba(0,0,0,0.07)")
        st.plotly_chart(fig_var, use_container_width=True)

    with col_d:
        dif_seg = resumo_seg[resumo_seg["DIFERENÇA"] != 0].sort_values("DIFERENÇA", ascending=True)
        cores_dif = ["#dc2626" if v > 0 else "#059669" for v in dif_seg["DIFERENÇA"]]

        fig_dif = go.Figure(go.Bar(
            y=dif_seg["SEGMENTO"],
            x=dif_seg["DIFERENÇA"],
            orientation="h",
            marker_color=cores_dif,
            marker_line_width=0,
            hovertemplate="<b>%{y}</b><br>Diferença: R$ %{x:,.2f}<extra></extra>",
        ))
        fig_dif.update_layout(
            title="Diferença de frete por segmento",
            xaxis=dict(tickprefix="R$ ", tickfont=dict(size=10)),
            yaxis=dict(tickfont=dict(size=10)),
            margin=dict(t=40,b=20,l=10,r=20),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_dif.update_xaxes(gridcolor="rgba(0,0,0,0.07)")
        fig_dif.update_yaxes(showgrid=False)
        st.plotly_chart(fig_dif, use_container_width=True)

    # ── Top notas com maior variação ──────────────
    st.markdown('<div class="section-header">🔝 Notas com maior variação de frete</div>', unsafe_allow_html=True)
    maiores = (
        df[df["DIFERENÇA FRETE"] != 0]
        .sort_values("DIFERENÇA FRETE", ascending=False)
        .head(15)
    )
    if maiores.empty:
        st.info("Nenhuma nota teve alteração de frete.")
    else:
        def fmt_zona(z):
            cls = {"Capital":"badge-capital","RM":"badge-rm"}.get(z,"badge-interior")
            return f'<span class="badge {cls}">{z}</span>'
        def fmt_dif(v):
            if v > 0: return f'<span class="badge badge-pos">+{moeda_br(v)}</span>'
            if v < 0: return f'<span class="badge badge-neg">{moeda_br(v)}</span>'
            return f'<span class="badge badge-zero">—</span>'

        disp = maiores[["Nº","MUNICÍPIO","ZONA","TIPO FRETE","DESCRIÇÃO DO PRODUTO / SERVIÇO","VALOR FRETE ANTIGO","VALOR FRETE","DIFERENÇA FRETE"]].copy()
        disp["ZONA"]            = disp["ZONA"].apply(fmt_zona)
        disp["VALOR FRETE ANTIGO"] = disp["VALOR FRETE ANTIGO"].apply(moeda_br)
        disp["VALOR FRETE"]        = disp["VALOR FRETE"].apply(moeda_br)
        disp["DIFERENÇA FRETE"]    = disp["DIFERENÇA FRETE"].apply(fmt_dif)
        disp.columns = ["NF","Município","Zona","Tipo","Descrição","Frete Ant.","Frete Novo","Diferença"]
        st.write(disp.to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

    # ── Tabela resumo por segmento ─────────────────
    with st.expander("📋 Resumo completo por zona × tipo"):
        resumo_seg["TOTAL_ANTIGO"] = resumo_seg["TOTAL_ANTIGO"].apply(moeda_br)
        resumo_seg["TOTAL_NOVO"]   = resumo_seg["TOTAL_NOVO"].apply(moeda_br)
        resumo_seg["DIFERENÇA"]    = resumo_seg["DIFERENÇA"].apply(moeda_br)
        st.dataframe(
            resumo_seg[["ZONA","TIPO FRETE","QTD","TOTAL_ANTIGO","TOTAL_NOVO","DIFERENÇA"]].rename(columns={
                "TIPO FRETE":"Tipo","QTD":"Qtd","TOTAL_ANTIGO":"Antigo","TOTAL_NOVO":"Novo","DIFERENÇA":"Variação"
            }),
            use_container_width=True, hide_index=True,
        )

    with st.expander("🔍 Todas as notas extraídas"):
        st.dataframe(df, use_container_width=True)


# ──────────────────────────────────────────────
# APP PRINCIPAL
# ──────────────────────────────────────────────

st.title("📄 Extrator NF-e → Excel (por cliente)")
st.caption("Escolha o cliente e envie o arquivo no formato correto.")
st.write("")

cliente = st.selectbox("👤 Selecione o cliente", CLIENTES, index=0)
st.write("")
st.divider()

# ── PLUMA ─────────────────────────────────────
if cliente.startswith("PLUMA"):
    st.subheader("📌 PLUMA ESPUMAS LTDA — Upload TXT ou PDF")
    st.caption("Envie o TXT extraído ou o PDF da NF-e. O Excel já sai com produto, tipo de frete e valor pela nova tabela.")

    uploaded = st.file_uploader("Selecione o arquivo TXT ou PDF", type=["txt","pdf"], accept_multiple_files=False)
    if uploaded is None:
        st.info("Faça o upload do TXT/PDF para iniciar a extração.")
        st.stop()

    try:
        texto = extrair_texto_upload(uploaded)
    except Exception as e:
        st.error(f"Não consegui ler o arquivo: {e}"); st.stop()

    with st.spinner("Extraindo dados..."):
        registros = extrair_notas_de_texto(texto)

    if not registros:
        st.warning("Não encontrei notas no arquivo. Verifique o layout."); st.stop()

    origem = detectar_origem_por_municipios(registros)
    st.caption(f"🏁 Origem detectada automaticamente: **{origem}**")

    excel_bytes, df = salvar_excel_bytes_pluma(registros, origem)

    # ── DOWNLOAD ──────────────────────────────────
    st.download_button(
        label="⬇️ Baixar Excel extraído (PLUMA)",
        data=excel_bytes,
        file_name="pluma_notas_extraidas_nova_tabela.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()

    # ── DASHBOARD MELHORADO ───────────────────────
    dashboard_pluma(df, origem)

    # ── MAPA ─────────────────────────────────────
    st.markdown('<div class="section-header">🗺️ Mapa ilustrativo dos destinos</div>', unsafe_allow_html=True)
    cache_col1, _ = st.columns([1,3])
    with cache_col1:
        if st.button("🧹 Limpar cache de coordenadas"):
            st.session_state["geocache"] = {}
            try:
                if os.path.exists(GEOCACHE_FILE): os.remove(GEOCACHE_FILE)
            except Exception: pass
            st.success("Cache limpo! Gere o mapa novamente.")

    if "geocache" not in st.session_state:
        st.session_state["geocache"] = load_geocache()

    municipios_series = (
        df["MUNICÍPIO"].dropna().astype(str)
        .map(sanitize_municipio_name).str.strip()
        .replace("", pd.NA).dropna()
    )
    contagem_municipios = municipios_series.value_counts().to_dict()
    municipios = list(contagem_municipios.keys())
    origem_norm = strip_accents_upper(origem)
    uf_origem   = "AL" if "MACEIO" in origem_norm else "PE"

    pontos, nao_plotados = [], []
    for mun in municipios:
        z, _ = classificar_zona_para_mapa(mun, origem)
        latlon = geocode_city(mun, uf_origem)
        if latlon:
            lat, lon = latlon
            pontos.append({
                "municipio": f"{mun}, {uf_origem}", "lat": lat, "lon": lon,
                "ZONA": z, "QTD_ENTREGAS": int(contagem_municipios.get(mun, 1)),
            })
        else:
            nao_plotados.append(mun)

    df_map = pd.DataFrame(pontos)
    st.caption(f"🗺️ Plotados: {len(df_map)} | Municípios distintos no arquivo: {len(municipios)}")
    build_map_folium(df_map, origem)

    if nao_plotados:
        st.caption("⚠️ Municípios não plotados (sem coordenadas): " + ", ".join(sorted(set(nao_plotados))))

# ── NORSA ─────────────────────────────────────
else:
    st.subheader("📌 NORSA REFRIGERANTES S.A — Upload XML")
    st.caption("Envie um ou vários XMLs de NF-e. Eu extraio os campos e gero uma planilha única.")

    files = st.file_uploader("Arraste aqui seus XMLs (pode mandar vários)", type=["xml"], accept_multiple_files=True)
    if not files:
        st.info("Envie os XMLs acima para começar."); st.stop()

    rows, erros = [], []
    for f in files:
        try:
            row = parse_nfe_xml(f.getvalue()); row["_arquivo"] = f.name; rows.append(row)
        except Exception as e:
            erros.append({"arquivo": f.name, "erro": str(e)})

    if erros:
        st.warning("Alguns arquivos não puderam ser processados.")
        st.dataframe(pd.DataFrame(erros), use_container_width=True)

    if rows:
        df = pd.DataFrame(rows)
        cols = ["Nº","NOME / RAZÃO SOCIAL","ENDEREÇO","BAIRRO / DISTRITO","MUNICÍPIO","CEP",
                "V. TOTAL DA NOTA","CÓDIGO PRODUTO","DESCRIÇÃO DO PRODUTO / SERVIÇO","QTDE PRODUTO",
                "QUANTIDADE","PESO BRUTO","TELEFONE / FAX","_arquivo"]
        df = df[[c for c in cols if c in df.columns]]

        st.subheader("✅ Resultado (NORSA)")
        st.dataframe(df, use_container_width=True)

        excel_bytes = salvar_excel_bytes_norsa(df)
        st.download_button(
            "⬇️ Baixar Excel (.xlsx) (NORSA)", data=excel_bytes,
            file_name="norsa_extracao_nfe.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )