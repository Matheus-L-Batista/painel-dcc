from __future__ import annotations

import os
import time

import pandas as pd

from utils.runtime import get_cache_dir


URL_PROCESSOS = (
    "https://docs.google.com/spreadsheets/d/"
    "1YNg6WRww19Gf79ISjQtb8tkzjX2lscHirnR_F3wGjog/"
    "gviz/tq?tqx=out:csv&sheet=BI%20-%20Itajub%C3%A1"
)

CACHE_FILE = get_cache_dir("processos_de_compras") / "processos_de_compras.parquet"
CACHE_TTL_SECONDS = int(os.environ.get("PROCESSOS_CACHE_TTL_SECONDS", "3600"))

COL_SOLICITANTE = "Solicitante"
COL_NUM_PROC = "Numero do Processo"
COL_PRECO_ESTIMADO = "PREÇO ESTIMADO"
COL_VALOR_CONTRATADO = "Valor Contratado"
COL_OBJETO = "Objeto"
COL_MODALIDADE = "Modalidade"
COL_ANO = "Ano"
COL_STATUS = "Status"
COL_CLASSIF_NC = "Classificação dos processos não concluídos"
COL_NUMERO = "Número"
COL_DATA_ENTRADA = "Data de Entrada"
COL_DATA_FINALIZACAO = "Data finalização"
COL_CONTR_REINSTR_COM = (
    "CONTRATAÇÃO REINSTRUÍDA PELO PROCESSO Nº (com pontos e traços)"
)

EXPECTED_COLUMNS = [
    COL_SOLICITANTE,
    COL_NUM_PROC,
    COL_PRECO_ESTIMADO,
    COL_VALOR_CONTRATADO,
    COL_OBJETO,
    COL_MODALIDADE,
    COL_ANO,
    COL_STATUS,
    COL_CLASSIF_NC,
    COL_NUMERO,
    COL_DATA_ENTRADA,
    COL_DATA_FINALIZACAO,
    COL_CONTR_REINSTR_COM,
]

MESES_ORDENADOS = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]

MESES_MAP = {numero: mes for numero, mes in enumerate(MESES_ORDENADOS, start=1)}

_DF_MEM = None
_DF_MEM_TS = 0.0


def formatar_moeda_brl(valor):
    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return (
        f"R$ {valor_float:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _cache_is_fresh(path, ttl_seconds: int) -> bool:
    try:
        if not path.exists():
            return False
        age = time.time() - path.stat().st_mtime
        return age < ttl_seconds
    except Exception:
        return False


def _has_expected_schema(df: pd.DataFrame) -> bool:
    return set(EXPECTED_COLUMNS).issubset(df.columns)


def carregar_dados_processos():
    df = pd.read_csv(URL_PROCESSOS)
    df.columns = [c.strip() for c in df.columns]

    for coluna in EXPECTED_COLUMNS:
        if coluna not in df.columns:
            df[coluna] = ""

    def conv_moeda(v):
        if isinstance(v, str):
            v = v.replace("R$", "").replace(".", "").replace(",", ".").strip()
            return float(v) if v not in ["", "-"] else 0.0
        return float(v) if pd.notna(v) else 0.0

    df[COL_PRECO_ESTIMADO] = df[COL_PRECO_ESTIMADO].apply(conv_moeda)
    df[COL_VALOR_CONTRATADO] = df[COL_VALOR_CONTRATADO].apply(conv_moeda)

    df[COL_DATA_FINALIZACAO] = pd.to_datetime(
        df[COL_DATA_FINALIZACAO], format="%d/%m/%Y", errors="coerce"
    )

    df["Mes_finalizacao"] = df[COL_DATA_FINALIZACAO].dt.month.map(MESES_MAP)
    return df


def get_df_processos(force: bool = False):
    global _DF_MEM, _DF_MEM_TS

    now = time.time()

    if (
        (not force)
        and (_DF_MEM is not None)
        and ((now - _DF_MEM_TS) < CACHE_TTL_SECONDS)
        and _has_expected_schema(_DF_MEM)
    ):
        return _DF_MEM.copy(), f"cache em memória ({int(now - _DF_MEM_TS)}s)"

    if (not force) and _cache_is_fresh(CACHE_FILE, CACHE_TTL_SECONDS):
        try:
            df_disk = pd.read_parquet(CACHE_FILE)
            if _has_expected_schema(df_disk):
                _DF_MEM = df_disk
                _DF_MEM_TS = now
                age = int(now - CACHE_FILE.stat().st_mtime)
                return df_disk.copy(), f"cache em disco ({age}s)"
        except Exception:
            pass

    df_new = carregar_dados_processos()
    try:
        df_new.to_parquet(CACHE_FILE, index=False)
    except Exception:
        pass

    _DF_MEM = df_new
    _DF_MEM_TS = now
    return df_new.copy(), "atualizado da planilha"
