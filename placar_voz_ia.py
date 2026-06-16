"""
PLACAR NEURON — Voz + HTML + Arduino + IA (Vosk + Gemini)
"""

# ============================================================
# BIBLIOTECAS
# ============================================================
import os
import sys
import json
import time
import getpass
import threading
import webbrowser
import unicodedata
import warnings

import vosk
import serial
import sounddevice as sd
import google.generativeai as genai
from flask import Flask, jsonify, send_file

# Configurações globais de terminal
vosk.SetLogLevel(-1)
warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURAÇÕES GERAIS E CONSTANTES
# ============================================================
MODEL_PATH      = "vosk-model-small-pt-0.3"
SERIAL_PORT     = "COM3"
BAUD_RATE       = 9600
SAMPLERATE      = 16000
FLASK_PORT      = 8080
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# UTILITÁRIOS
# ============================================================
def limpar_tela():
    os.system('cls' if os.name == 'nt' else 'clear')
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()

def limpar_texto(txt):
    """Remove acentos e converte para minúsculas."""
    if not txt: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn').lower().strip()

# ============================================================
# INICIALIZAÇÃO DA INTELIGÊNCIA ARTIFICIAL
# ============================================================
limpar_tela()
print("=" * 55)
print("  INICIALIZAÇÃO DO SISTEMA — PLACAR NEURON")
print("=" * 55)
CHAVE_API = getpass.getpass(" Cole sua chave API do Gemini (invisível) e aperte Enter: ").strip()

if not CHAVE_API:
    print("\n[ERRO] Nenhuma chave fornecida. Encerrando o sistema.")
    exit()

try:
    genai.configure(api_key=CHAVE_API)
    modelo_ia = genai.GenerativeModel('gemini-1.5-flash-latest')
except Exception as e:
    print(f"\n[ERRO] Falha ao configurar o Gemini: {e}"); exit()

# ============================================================
# BANCO DE DADOS E ESTADO DO JOGO
# ============================================================
with open(os.path.join(DIRETORIO_ATUAL, "enigmas.json"), encoding="utf-8") as f:
    ENIGMAS = json.load(f)

estado = {
    "enigma_index": 0, "tela": "pergunta", "total": len(ENIGMAS),
    "feedback": None, "feedback_contador": 0,
    "ultima_acao": "Sistema pronto. Aguardando comando..."
}

COMANDOS_ENIGMA = {
    "pergunta seguinte": "proximo", "enigma seguinte": "proximo", "seguinte": "proximo",
    "mostrar resposta": "resposta", "revelar resposta": "resposta",
    "mostrar pergunta": "pergunta", "voltar": "anterior", "enigma anterior": "anterior",
}

COMANDOS_ARDUINO = {
    "ponto pulso vermelho": 'R', "ponto pulso verde": 'G', "ponto pulso azul": 'B', "ponto pulso amarelo": 'Y',
    "dois pontos pulso vermelho": 'Q', "dois pontos pulso verde": 'H', "dois pontos pulso azul": 'C', "dois pontos pulso amarelo": 'Z',
    "menos ponto pulso vermelho": 'r', "menos ponto pulso verde": 'g', "menos ponto pulso azul": 'b', "menos ponto pulso amarelo": 'y',
    "zerar pulso vermelho": 'w', "zerar pulso verde": 'h', "zerar pulso azul": 'c', "zerar pulso amarelo": 'z',
    "zerar tudo": 'X',
}

IGNORAR = {"o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "por", "para", "com", "que", "e", "é", "eu", "não"}

# ============================================================
# HARDWARE (ARDUINO) E INTERFACE
# ============================================================
arduino = None
def conectar_arduino():
    global arduino
    try:
        arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(1)
        print(f" [OK] Arduino conectado na porta {SERIAL_PORT}.")
    except:
        print(" [AVISO] Arduino não detectado. Modo offline ativo.")

def atualizar_painel(mensagem_acao=""):
    if mensagem_acao: estado["ultima_acao"] = mensagem_acao
    limpar_tela()
    print("=" * 55)
    print("  PLACAR NEURON — Painel de Controle (Vosk + IA)")
    print("=" * 55)
    print(f"  Enigma Atual : {estado['enigma_index'] + 1} de {estado['total']}")
    print(f"  Última Ação  : {estado['ultima_acao']}")
    print("  Microfone    : [ LIGADO ] Escutando comandos...")
    print("=" * 55)
    print(f"  Painel Web   : http://localhost:{FLASK_PORT}")
    print("  (Pressione Ctrl+C para encerrar)\n")

def limpar_feedback():
    estado["feedback"] = None; atualizar_painel()

# ============================================================
# LÓGICA DE PROCESSAMENTO E INTELIGÊNCIA ARTIFICIAL
# ============================================================
def corrigir_comando_com_ia(texto_bruto, enigma_atual):
    """Filtra a voz pelo Gemini para corrigir erros de pronúncia e intenção."""
    texto = limpar_texto(texto_bruto)
    if not texto or texto == "[unk]": return ""

    resposta_certa = limpar_texto(enigma_atual["resposta"])
    alternativas = [limpar_texto(alt) for alt in enigma_atual.get("alternativas", [])]

    # Bypass Rápido: Se bater perfeitamente com os comandos ou respostas, não gasta cota da API
    if texto in COMANDOS_ENIGMA or texto in COMANDOS_ARDUINO or texto == resposta_certa or texto in alternativas:
        return texto

    # Acionamento da IA para correção de contexto
    banco_de_dados = f"{list(COMANDOS_ENIGMA.keys())}, {list(COMANDOS_ARDUINO.keys())}, '{resposta_certa}', {alternativas}"
    prompt = f"Você é um classificador algorítmico. BANCO DE DADOS: {banco_de_dados}. Texto com erro: '{texto}'. Regra: Devolva EXATAMENTE E APENAS uma chave do banco de dados que corresponda à intenção. Se não houver relação, devolva: ignorar"

    try:
        resultado = modelo_ia.generate_content(prompt).text.strip().lower().replace("'", "").replace('"', '')
        return "" if resultado == "ignorar" else resultado
    except:
        return texto

def processar_texto(texto):
    """Recebe o texto já corrigido pela IA e executa a ação."""
    texto = texto.lower().strip()

    # Navegação Web
    for frase, acao in COMANDOS_ENIGMA.items():
        if frase in texto:
            estado["feedback"] = None; executar_acao_enigma(acao); return

    # Hardware (Arduino)
    for frase, cmd in COMANDOS_ARDUINO.items():
        if frase in texto:
            if arduino and arduino.is_open:
                arduino.write(cmd.encode())
                atualizar_painel(f"Sinal do painel enviado (Código: {cmd})")
            else:
                atualizar_painel(f"Ignorado: Arduino desconectado ({cmd})")
            return

    # Segurança
    if estado["tela"] != "pergunta": return

    enigma = ENIGMAS[estado["enigma_index"]]
    resposta_correta = limpar_texto(enigma["resposta"])
    alternativas_erradas = [limpar_texto(a) for a in enigma.get("alternativas", []) if limpar_texto(a) != resposta_correta]

    # Validação
    if resposta_correta in texto:
        estado["feedback"] = None; estado["tela"] = "resposta"
        atualizar_painel(f"ACERTO! Resposta validada: '{enigma['resposta']}'"); return

    for alt_errada in alternativas_erradas:
        if alt_errada in texto:
            estado["feedback"] = "erro"; estado["feedback_contador"] += 1
            atualizar_painel(f"Errou: Escolheu alternativa incorreta '{alt_errada}'")
            threading.Timer(8.0, limpar_feedback).start(); return

    # Ruído
    if [p for p in texto.split() if p not in IGNORAR and len(p) > 2]:
        estado["feedback"] = "erro"; estado["feedback_contador"] += 1
        atualizar_painel(f"Voz não reconhecida ou ruído: '{texto}'")
        threading.Timer(8.0, limpar_feedback).start()

def executar_acao_enigma(acao):
    idx, total = estado["enigma_index"], estado["total"]
    if acao == "proximo" and idx < total - 1:
        estado["enigma_index"] += 1; estado["tela"] = "pergunta"
        atualizar_painel(f"Avançou para o Enigma {estado['enigma_index'] + 1}")
    elif acao == "anterior" and idx > 0:
        estado["enigma_index"] -= 1; estado["tela"] = "pergunta"
        atualizar_painel(f"Voltou para o Enigma {estado['enigma_index'] + 1}")
    elif acao == "resposta":
        estado["tela"] = "resposta"; atualizar_painel("Tela atualizada para: Mostrar Resposta")
    elif acao == "pergunta":
        estado["tela"] = "pergunta"; atualizar_painel("Tela atualizada para: Mostrar Pergunta")

# ============================================================
# SERVIDOR WEB (FLASK)
# ============================================================
app = Flask(__name__)

@app.route("/")
def index(): return send_file(os.path.join(DIRETORIO_ATUAL, "perguntas.html"))

@app.route("/Estampa_Neuron.png")
def estampa():
    try: return send_file(os.path.join(DIRETORIO_ATUAL, "Estampa_Neuron.png"))
    except: return "", 404

@app.route("/estado")
def get_estado():
    idx = estado["enigma_index"]
    enigma = ENIGMAS[idx]
    return jsonify({
        "enigma_index": idx, "enigma_numero": idx + 1, "total": estado["total"],
        "tela": estado["tela"], "pergunta": enigma["pergunta"], "resposta": enigma["resposta"],
        "alternativas": enigma.get("alternativas", []), "feedback": estado["feedback"],
        "feedback_contador": estado["feedback_contador"]
    })

@app.route("/proximo")
def proximo(): estado["feedback"] = None; executar_acao_enigma("proximo"); return "", 204
@app.route("/anterior")
def anterior(): estado["feedback"] = None; executar_acao_enigma("anterior"); return "", 204
@app.route("/resposta")
def mostrar_resposta(): estado["tela"] = "resposta"; atualizar_painel("Tela atualizada: Resposta"); return "", 204
@app.route("/pergunta")
def mostrar_pergunta(): estado["tela"] = "pergunta"; atualizar_painel("Tela atualizada: Pergunta"); return "", 204

def iniciar_flask():
    print(f"\n[SISTEMA] Iniciando servidor web na porta {FLASK_PORT}...")
    app.run(port=FLASK_PORT, debug=False, use_reloader=False)

# ============================================================
# MICROFONE E MULTITHREADING (VOSK)
# ============================================================
def fluxo_ia_e_processamento(texto_bruto):
    comando_revisado = corrigir_comando_com_ia(texto_bruto, ENIGMAS[estado["enigma_index"]])
    if comando_revisado: processar_texto(comando_revisado)

def iniciar_vosk():
    print(" [Aguarde] Carregando o modelo acústico...")
    model = vosk.Model(MODEL_PATH)
    
    vocabulario = set(["[unk]", "sim", "nao", "dica"])
    for cmd in list(COMANDOS_ENIGMA.keys()) + list(COMANDOS_ARDUINO.keys()): vocabulario.add(limpar_texto(cmd))
    for enigma in ENIGMAS: 
        vocabulario.add(limpar_texto(enigma["resposta"]))
        for alt in enigma.get("alternativas", []): vocabulario.add(limpar_texto(alt))
        
    rec = vosk.KaldiRecognizer(model, SAMPLERATE, json.dumps(list(vocabulario)))
    atualizar_painel("Sistema iniciado com sucesso e escutando.")

    def callback(indata, frames, time_info, status):
        if rec.AcceptWaveform(bytes(indata)):
            texto_bruto = json.loads(rec.Result()).get("text", "").strip()
            if texto_bruto:
                threading.Thread(target=fluxo_ia_e_processamento, args=(texto_bruto,), daemon=True).start()

    with sd.RawInputStream(samplerate=SAMPLERATE, blocksize=8000, dtype="int16", channels=1, callback=callback):
        while True: sd.sleep(100)

# ============================================================
# GATILHO DE PARTIDA (MAIN)
# ============================================================
if __name__ == "__main__":
    limpar_tela()
    print("=" * 55); print("  CARREGANDO MÓDULOS DE SISTEMA..."); print("=" * 55)
    
    conectar_arduino()
    threading.Thread(target=iniciar_flask, daemon=True).start()
    
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{FLASK_PORT}")

    try:
        iniciar_vosk()
    except KeyboardInterrupt:
        limpar_tela(); print("\n=" * 55); print("  SISTEMA ENCERRADO COM SUCESSO. ATÉ LOGO!"); print("=" * 55 + "\n")
    finally:
        if arduino and arduino.is_open: arduino.close()
