"""
=============================================================
  MOTOR DE BUSCA B2B — Sprint 1 (Duffel Air API)
  Ambiente : Duffel — Test Environment (token de teste)
  Objetivo : Buscar voos, filtrar o melhor preço via pandas
             e imprimir proposta formatada com margem de lucro.
=============================================================
"""

import os
import sys
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

# ─────────────────────────────────────────────
# 1. CONFIGURAÇÃO — carrega variáveis do .env
# ─────────────────────────────────────────────
load_dotenv()

DUFFEL_TOKEN = os.getenv("DUFFEL_ACCESS_TOKEN")
MARGEM       = float(os.getenv("MARGEM_LUCRO", "0.15"))

BASE_URL     = "https://api.duffel.com"

if not DUFFEL_TOKEN or "AQUI" in DUFFEL_TOKEN:
    print("⚠  ATENÇÃO: Preencha DUFFEL_ACCESS_TOKEN no arquivo .env")
    sys.exit(1)


# ─────────────────────────────────────────────
# 2. AUTENTICAÇÃO — Duffel usa API Key direta
#    (sem OAuth2 — o token do .env já é o Bearer)
# ─────────────────────────────────────────────
def obter_headers() -> dict:
    """Retorna os headers padrão para todas as chamadas à API Duffel."""
    return {
        "Authorization" : f"Bearer {DUFFEL_TOKEN}",
        "Accept"        : "application/json",
        "Accept-Encoding": "gzip",
        "Duffel-Version": "v2",
        "Content-Type"  : "application/json",
    }


# ─────────────────────────────────────────────
# 3. BUSCA DE VOOS — POST /air/offer_requests
# ─────────────────────────────────────────────
def buscar_voos(origem: str, destino: str,
                data_ida: str, data_volta: str,
                adultos: int = 1) -> list:
    """
    Cria um Offer Request na Duffel com ida e volta.
    Retorna a lista de ofertas já embutida na resposta
    (parâmetro return_offers=true).
    """
    url = f"{BASE_URL}/air/offer_requests"
    headers = obter_headers()

    # Monta os passageiros
    passengers = [{"type": "adult"} for _ in range(adultos)]

    body = {
        "data": {
            "slices": [
                {   # Ida
                    "origin"        : origem,
                    "destination"   : destino,
                    "departure_date": data_ida,
                },
                {   # Volta
                    "origin"        : destino,
                    "destination"   : origem,
                    "departure_date": data_volta,
                },
            ],
            "passengers"  : passengers,
            "cabin_class" : "economy",
        }
    }

    # return_offers=true traz as ofertas diretamente na resposta
    resposta = requests.post(
        url,
        headers=headers,
        json=body,
        params={"return_offers": "true"},
        timeout=30,
    )
    resposta.raise_for_status()

    ofertas = resposta.json().get("data", {}).get("offers", [])
    print(f"[✓] {len(ofertas)} opções de voo recebidas da Duffel\n")
    return ofertas


# ─────────────────────────────────────────────
# 4. PROCESSAMENTO — pandas filtra e rankeia
# ─────────────────────────────────────────────
def processar_voos(dados: list) -> pd.DataFrame:
    """
    Parseia a lista de ofertas Duffel.
    Considera apenas o primeiro slice (ida) para rankear;
    o preço já é o total da ida+volta.
    """
    registros = []
    for oferta in dados:
        preco_total = float(oferta["total_amount"])
        moeda       = oferta["total_currency"]

        # Slice 0 = ida  |  Slice 1 = volta (se round-trip)
        slice_ida   = oferta["slices"][0]
        segmentos   = slice_ida["segments"]
        num_paradas = len(segmentos) - 1

        # Duração total do slice de ida (ex: "PT3H15M")
        duracao_raw = slice_ida.get("duration", "N/A")

        primeiro_seg = segmentos[0]
        ultimo_seg   = segmentos[-1]

        partida   = primeiro_seg["origin"]["iata_code"]
        chegada   = ultimo_seg["destination"]["iata_code"]
        cia_aerea = primeiro_seg["marketing_carrier"]["iata_code"]
        num_voo   = primeiro_seg.get("marketing_carrier_flight_number", "")
        hora_part = primeiro_seg["departing_at"]
        hora_cheg = ultimo_seg["arriving_at"]

        registros.append({
            "oferta_id"   : oferta["id"],
            "cia_aerea"   : cia_aerea,
            "voo"         : f"{cia_aerea}{num_voo}",
            "partida"     : partida,
            "chegada"     : chegada,
            "hora_partida": hora_part,
            "hora_chegada": hora_cheg,
            "duracao"     : duracao_raw,
            "paradas"     : num_paradas,
            "preco_brl"   : preco_total,
            "moeda"       : moeda,
        })

    df = pd.DataFrame(registros)

    # ── Filtros de qualidade ──────────────────
    # Descarta voos com mais de 2 conexões
    df = df[df["paradas"] <= 2]

    # Ordena pelo menor preço
    df = df.sort_values("preco_brl").reset_index(drop=True)

    return df


# ─────────────────────────────────────────────
# 5. SELEÇÃO DO MELHOR VOO
# ─────────────────────────────────────────────
def selecionar_melhor(df: pd.DataFrame) -> pd.Series:
    return df.iloc[0]


# ─────────────────────────────────────────────
# 6. CÁLCULO DE MARGEM
# ─────────────────────────────────────────────
def calcular_proposta(preco_bruto: float, margem: float) -> dict:
    comissao      = preco_bruto * margem
    preco_cliente = preco_bruto + comissao
    return {
        "preco_bruto"  : preco_bruto,
        "comissao"     : comissao,
        "preco_cliente": preco_cliente,
        "margem_pct"   : margem * 100,
    }


# ─────────────────────────────────────────────
# 7. OUTPUT — proposta formatada no terminal
# ─────────────────────────────────────────────
def imprimir_proposta(voo: pd.Series, proposta: dict,
                      origem: str, destino: str,
                      data_ida: str, data_volta: str):

    hora_part_fmt = voo["hora_partida"].replace("T", " às ")
    hora_cheg_fmt = voo["hora_chegada"].replace("T", " às ")

    print("=" * 60)
    print("       PROPOSTA DE VIAGEM — TURISMO B2B")
    print("=" * 60)
    print(f"  Rota        : {origem}  →  {destino}")
    print(f"  Ida         : {data_ida}   |   Volta: {data_volta}")
    print("-" * 60)
    print(f"  Companhia   : {voo['cia_aerea']}")
    print(f"  Voo         : {voo['voo']}")
    print(f"  Partida     : {hora_part_fmt}")
    print(f"  Chegada     : {hora_cheg_fmt}")
    print(f"  Conexões    : {voo['paradas']}")
    print(f"  Duração     : {voo['duracao']}")
    print("-" * 60)
    print(f"  Tarifa bruta: R$ {proposta['preco_bruto']:,.2f}")
    print(f"  Comissão ({proposta['margem_pct']:.0f}%): R$ {proposta['comissao']:,.2f}")
    print(f"  ★ VALOR CLIENTE: R$ {proposta['preco_cliente']:,.2f}")
    print("=" * 60)
    print(f"  Gerado em   : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)


# ─────────────────────────────────────────────
# 8. MAIN — orquestrador da Sprint 1
# ─────────────────────────────────────────────
def main():
    # ── Parâmetros da busca (Input) ───────────
    ORIGEM     = "GRU"
    DESTINO    = "BSB"
    DATA_IDA   = "2026-10-20"
    DATA_VOLTA = "2026-10-25"
    ADULTOS    = 1

    print("\n" + "=" * 60)
    print("  MOTOR DE BUSCA B2B — Duffel Air API")
    print("=" * 60)
    print(f"  Buscando: {ORIGEM} → {DESTINO}")
    print(f"  Datas   : {DATA_IDA}  a  {DATA_VOLTA}")
    print(f"  Margem  : {MARGEM * 100:.0f}%")
    print("=" * 60 + "\n")

    # Etapa 1 — Busca de voos (sem OAuth2 — chave direta)
    dados_brutos = buscar_voos(ORIGEM, DESTINO,
                               DATA_IDA, DATA_VOLTA, ADULTOS)

    if not dados_brutos:
        print("Nenhum voo encontrado para os critérios informados.")
        return

    # Etapa 2 — Processamento e filtragem (pandas)
    df_voos = processar_voos(dados_brutos)
    print(f"[✓] {len(df_voos)} voos após filtros de qualidade\n")

    # Etapa 3 — Seleção do melhor
    melhor_voo = selecionar_melhor(df_voos)

    # Etapa 4 — Cálculo da proposta com margem
    proposta = calcular_proposta(melhor_voo["preco_brl"], MARGEM)

    # Etapa 5 — Output formatado
    imprimir_proposta(melhor_voo, proposta,
                      ORIGEM, DESTINO, DATA_IDA, DATA_VOLTA)


if __name__ == "__main__":
    main()
