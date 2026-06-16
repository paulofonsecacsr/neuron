"""
PLACAR NEURON — Voz + HTML + Arduino
Reconhecimento: faster-whisper (offline) com VAD
Validação: Dicionário de correção (Força Bruta)
Interface: Log contínuo no terminal
"""

import os, sys, json, queue, threading, time, unicodedata, warnings, webbrowser
import numpy as np
import serial
import sounddevice as sd
from faster_whisper import WhisperModel
from flask import Flask, jsonify, send_file

warnings.filterwarnings("ignore")

# --- CONFIGURAÇÕES ---
WHISPER_MODEL, WHISPER_DEVICE, COMPUTE_TYPE = "small", "cpu", "int8"
SERIAL_PORT, BAUD_RATE = "COM3", 9600
SAMPLERATE, FLASK_PORT = 16000, 8080

# --- PARÂMETROS VAD ---
SILENCIO_LIMIAR, SILENCIO_BLOCOS, MIN_BLOCOS_FALA, PRE_ROLL_BLOCOS, BLOCKSIZE = 250, 4, 2, 3, 4000

# --- ESTADO E DADOS ---
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(DIRETORIO_ATUAL, "enigmas.json"), encoding="utf-8") as f:
    ENIGMAS = json.load(f)

estado = {"enigma_index": 0, "tela": "pergunta", "total": len(ENIGMAS), "feedback": None, "feedback_contador": 0}

CORRECOES_VOZ = {"flux": "flor", "vidao": "vida", "morti": "morte"}

COMANDOS_ENIGMA = {
    "próxima pergunta": "proximo", "proxima pergunta": "proximo", "próximo enigma": "proximo", "proximo enigma": "proximo",
    "seguinte": "proximo", "mostrar resposta": "resposta", "revelar resposta": "resposta", "mostrar pergunta": "pergunta",
    "voltar": "anterior", "enigma anterior": "anterior"
}

COMANDOS_ARDUINO = {
    "ponto vermelho": 'R', "ponto verde": 'G', "ponto azul": 'B', "ponto amarelo": 'Y',
    "dois pontos vermelho": 'Q', "2 pontos vermelho": 'Q', "dois pontos verde": 'H', "2 pontos verde": 'H',
    "dois pontos azul": 'C', "2 pontos azul": 'C', "dois pontos amarelo": 'Z', "2 pontos amarelo": 'Z',
    "menos ponto vermelho": 'r', "menos ponto verde": 'g', "menos ponto azul": 'b', "menos ponto amarelo": 'y',
    "zerar vermelho": 'w', "zerar verde": 'h', "zerar azul": 'c', "zerar amarelo": 'z', "zerar tudo": 'X'
}

# --- ARDUINO ---
arduino = None
def conectar_arduino():
    global arduino
    try:
        arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"[OK] Arduino conectado na porta {SERIAL_PORT}.")
    except:
        print("[AVISO] Arduino não detectado. Iniciando em modo offline.")

# --- LÓGICA DO JOGO ---
def limpar_texto(t): return ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn').lower().strip() if t else ""
def limpar_feedback(): estado["feedback"] = None

def processar_texto(texto):
    texto_limpo = limpar_texto(texto)
    print(f"\n[VOZ] Capturado: '{texto_limpo}'")

    for errado, certo in CORRECOES_VOZ.items():
        texto_limpo = texto_limpo.replace(errado, certo)
    if any(e in limpar_texto(texto) for e in CORRECOES_VOZ): print(f"[VOZ] Após correção: '{texto_limpo}'")

    for frase, acao in sorted(COMANDOS_ENIGMA.items(), key=lambda x: len(x[0]), reverse=True):
        if limpar_texto(frase) in texto_limpo:
            estado["feedback"] = None; executar_acao_enigma(acao); return

    for frase, cmd in sorted(COMANDOS_ARDUINO.items(), key=lambda x: len(x[0]), reverse=True):
        if limpar_texto(frase) in texto_limpo:
            if arduino and arduino.is_open: arduino.write(cmd.encode()); print(f"[LED] Comando '{cmd}' enviado.")
            else: print(f"[LED] Ignorado (Arduino offline) - '{cmd}'")
            return

    if estado["tela"] != "pergunta": return

    enigma = ENIGMAS[estado["enigma_index"]]
    resp_certa = limpar_texto(enigma["resposta"])
    alts_erradas = [limpar_texto(a) for a in enigma.get("alternativas", []) if limpar_texto(a) != resp_certa]

    if resp_certa in texto_limpo:
        estado.update({"feedback": None, "tela": "resposta"})
        print(f"[ACERTO] Resposta validada: '{enigma['resposta']}'")
        return

    for alt in alts_erradas:
        if alt in texto_limpo:
            estado["feedback"] = "erro"; estado["feedback_contador"] += 1
            print(f"[ERRO] Escolheu alternativa incorreta: '{alt}'")
            threading.Timer(8.0, limpar_feedback).start()
            return

def executar_acao_enigma(acao):
    idx, total = estado["enigma_index"], estado["total"]
    if acao == "proximo" and idx < total - 1:
        estado.update({"enigma_index": idx + 1, "tela": "pergunta"})
        print(f"[SISTEMA] Avançou para o Enigma {estado['enigma_index'] + 1}")
    elif acao == "anterior" and idx > 0:
        estado.update({"enigma_index": idx - 1, "tela": "pergunta"})
        print(f"[SISTEMA] Voltou para o Enigma {estado['enigma_index'] + 1}")
    elif acao in ["resposta", "pergunta"]:
        estado["tela"] = acao
        print(f"[SISTEMA] Tela atualizada: Mostrar {acao.capitalize()}")

# --- FLASK ---
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
    e = ENIGMAS[idx]
    return jsonify({"enigma_index": idx, "enigma_numero": idx + 1, "total": estado["total"], "tela": estado["tela"], "pergunta": e["pergunta"], "resposta": e["resposta"], "alternativas": e.get("alternativas", []), "feedback": estado["feedback"], "feedback_contador": estado["feedback_contador"]})
@app.route("/proximo")
def proximo(): estado["feedback"] = None; executar_acao_enigma("proximo"); return "", 204
@app.route("/anterior")
def anterior(): estado["feedback"] = None; executar_acao_enigma("anterior"); return "", 204
@app.route("/resposta")
def mostrar_resposta(): estado["tela"] = "resposta"; print("[SISTEMA] HTML: Mostrar Resposta"); return "", 204
@app.route("/pergunta")
def mostrar_pergunta(): estado["tela"] = "pergunta"; print("[SISTEMA] HTML: Mostrar Pergunta"); return "", 204
def iniciar_flask(): app.run(port=FLASK_PORT, debug=False, use_reloader=False)

# --- WHISPER & VAD ---
def iniciar_whisper():
    print("\n[Aguarde] Carregando o motor de voz (faster-whisper)...")
    model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=COMPUTE_TYPE)
    print("[OK] Sistema de voz pronto. Escutando comandos...\n")

    fila_audio = queue.Queue()
    def callback(indata, frames, time_info, status): fila_audio.put(bytes(indata))

    def transcrever(audio_bytes):
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio, language="pt", vad_filter=True, beam_size=1, initial_prompt="Comandos: próxima pergunta, mostrar resposta, ponto vermelho, zerar tudo.", condition_on_previous_text=False)
        return " ".join(s.text for s in segments).strip()

    from collections import deque
    buffer_fala, blocos_silencio, falando = [], 0, False
    pre_roll = deque(maxlen=PRE_ROLL_BLOCOS)

    with sd.RawInputStream(samplerate=SAMPLERATE, blocksize=BLOCKSIZE, dtype="int16", channels=1, callback=callback):
        while True:
            bloco = fila_audio.get()
            if np.abs(np.frombuffer(bloco, dtype=np.int16)).mean() >= SILENCIO_LIMIAR:
                if not falando: falando, buffer_fala = True, list(pre_roll)
                buffer_fala.append(bloco); blocos_silencio = 0
            else:
                if falando:
                    buffer_fala.append(bloco); blocos_silencio += 1
                    if blocos_silencio >= SILENCIO_BLOCOS:
                        if len(buffer_fala) >= MIN_BLOCOS_FALA:
                            texto = transcrever(b"".join(buffer_fala))
                            if texto: processar_texto(texto)
                        buffer_fala, blocos_silencio, falando = [], 0, False
                else: pre_roll.append(bloco)

# --- MAIN ---
if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 55 + "\n  PLACAR NEURON — INICIADO\n" + "=" * 55)
    
    conectar_arduino()
    threading.Thread(target=iniciar_flask, daemon=True).start()
    
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{FLASK_PORT}")

    try: iniciar_whisper()
    except KeyboardInterrupt: print("\n[SISTEMA] Encerrado pelo usuário. Até logo!")
    finally:
        if arduino and arduino.is_open: arduino.close()