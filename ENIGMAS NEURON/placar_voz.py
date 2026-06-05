"""
PLACAR NEURON — Voz + HTML + Arduino
"""


import json
import threading
import time


import serial
import sounddevice as sd
import vosk
from flask import Flask, jsonify, send_file, send_from_directory


# ============================================================
#  CONFIGURAÇÕES
# ============================================================


MODEL_PATH  = "vosk-model-small-pt-0.3"
SERIAL_PORT = "COM3"
BAUD_RATE   = 9600
SAMPLERATE  = 16000
FLASK_PORT  = 5000


# ============================================================
#  CARREGA ENIGMAS
# ============================================================


with open("enigmas.json", encoding="utf-8") as f:
    ENIGMAS = json.load(f)


# ============================================================
#  ESTADO DO JOGO
# ============================================================


estado = {
    "enigma_index":      0,
    "tela":              "pergunta",
    "total":             len(ENIGMAS),
    "feedback":          None,
    "feedback_contador": 0,
}


# ============================================================
#  COMANDOS DE VOZ
# ============================================================


COMANDOS_ENIGMA = {
    "próxima pergunta": "proximo",
    "proxima pergunta": "proximo",
    "próximo enigma":   "proximo",
    "proximo enigma":   "proximo",
    "mostrar resposta": "resposta",
    "revelar resposta": "resposta",
    "mostrar pergunta": "pergunta",
    "voltar":           "anterior",
    "enigma anterior":  "anterior",
}


COMANDOS_ARDUINO = {
    # +1 ponto
    "ponto pulso vermelho":  'R',
    "ponto pulso verde":     'G',
    "ponto pulso azul":      'B',
    "ponto pulso amarelo":   'Y',
    # +2 pontos
    "dois pontos pulso vermelho": 'Q',
    "dois pontos pulso verde":    'H',
    "dois pontos pulso azul":     'C',
    "dois pontos pulso amarelo":  'Z',
    # -1 ponto
    "menos ponto pulso vermelho": 'r',
    "menos ponto pulso verde":    'g',
    "menos ponto pulso azul":     'b',
    "menos ponto pulso amarelo":  'y',
    # zerar time
    "zerar pulso vermelho":  'w',
    "zerar pulso verde":     'h',
    "zerar pulso azul":      'c',
    "zerar pulso amarelo":   'z',
    # zerar tudo
    "zerar tudo":            'X',
}


IGNORAR = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na",
    "por", "para", "com", "que", "e", "é", "eu", "não"
}


# ============================================================
#  ARDUINO
# ============================================================


arduino = None


def conectar_arduino():
    global arduino
    try:
        arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"[OK] Arduino conectado em {SERIAL_PORT}")
    except Exception as e:
        print(f"[AVISO] Arduino não conectado: {e}")


# ============================================================
#  PROCESSAMENTO DE VOZ
# ============================================================


def limpar_feedback():
    estado["feedback"] = None


def processar_texto(texto):
    texto = texto.lower().strip()
    print(f"\n[VOZ] '{texto}'")


    # 1) Comandos de navegação
    for frase, acao in COMANDOS_ENIGMA.items():
        if frase in texto:
            estado["feedback"] = None
            executar_acao_enigma(acao)
            return


    # 2) Comandos do Arduino
    for frase, cmd in COMANDOS_ARDUINO.items():
        if frase in texto:
            if arduino and arduino.is_open:
                arduino.write(cmd.encode())
                print(f"[LED] Comando '{cmd}' enviado ao Arduino")
            else:
                print(f"[LED] Arduino desconectado — '{cmd}' ignorado")
            return


    # 3) Só verifica resposta se estiver na tela de pergunta
    if estado["tela"] != "pergunta":
        return


    # 4) Verifica se é a resposta correta
    idx_atual = estado["enigma_index"]
    resposta_correta = ENIGMAS[idx_atual]["resposta"].lower().strip()


    if resposta_correta in texto:
        print(f"[ACERTO] Resposta correta: '{resposta_correta}'")
        estado["feedback"] = None
        estado["tela"] = "resposta"
        return


    # 5) Resposta errada
    palavras = [p for p in texto.split() if p not in IGNORAR and len(p) > 2]
    if palavras:
        print(f"[ERRO] Resposta errada: '{texto}'")
        estado["feedback"] = "erro"
        estado["feedback_contador"] = estado["feedback_contador"] + 1
        threading.Timer(8.0, limpar_feedback).start()


def executar_acao_enigma(acao):
    idx   = estado["enigma_index"]
    total = estado["total"]


    if acao == "proximo":
        if idx < total - 1:
            estado["enigma_index"] += 1
            estado["tela"] = "pergunta"
            print(f"[ENIGMA] Avançou para enigma {estado['enigma_index'] + 1}")
        else:
            print("[ENIGMA] Já é o último enigma.")


    elif acao == "anterior":
        if idx > 0:
            estado["enigma_index"] -= 1
            estado["tela"] = "pergunta"
            print(f"[ENIGMA] Voltou para enigma {estado['enigma_index'] + 1}")
        else:
            print("[ENIGMA] Já é o primeiro enigma.")


    elif acao == "resposta":
        estado["tela"] = "resposta"


    elif acao == "pergunta":
        estado["tela"] = "pergunta"


# ============================================================
#  FLASK
# ============================================================


app = Flask(__name__)


@app.route("/")
def index():
    return send_file("perguntas.html")


@app.route("/Estampa_Neuron.png")
def estampa():
    return send_from_directory(".", "Estampa_Neuron.png")


@app.route("/estado")
def get_estado():
    idx = estado["enigma_index"]
    enigma = ENIGMAS[idx]
    return jsonify({
        "enigma_index":      idx,
        "enigma_numero":     idx + 1,
        "total":             estado["total"],
        "tela":              estado["tela"],
        "pergunta":          enigma["pergunta"],
        "resposta":          enigma["resposta"],
        "feedback":          estado["feedback"],
        "feedback_contador": estado["feedback_contador"],
    })


@app.route("/proximo")
def proximo():
    estado["feedback"] = None
    executar_acao_enigma("proximo")
    return ("", 204)


@app.route("/anterior")
def anterior():
    estado["feedback"] = None
    executar_acao_enigma("anterior")
    return ("", 204)


@app.route("/resposta")
def mostrar_resposta():
    estado["tela"] = "resposta"
    return ("", 204)


@app.route("/pergunta")
def mostrar_pergunta():
    estado["tela"] = "pergunta"
    return ("", 204)


def iniciar_flask():
    app.run(port=FLASK_PORT, debug=False, use_reloader=False)


# ============================================================
#  VOSK
# ============================================================


def iniciar_vosk():
    print("[VOZ] Carregando modelo...")
    model = vosk.Model(MODEL_PATH)
    rec   = vosk.KaldiRecognizer(model, SAMPLERATE)
    print("[VOZ] Pronto! Fale agora. (Ctrl+C para sair)\n")


    def callback(indata, frames, time_info, status):
        if rec.AcceptWaveform(bytes(indata)):
            resultado = json.loads(rec.Result())
            texto = resultado.get("text", "").strip()
            if texto:
                processar_texto(texto)


    with sd.RawInputStream(samplerate=SAMPLERATE, blocksize=8000,
                           dtype="int16", channels=1, callback=callback):
        while True:
            sd.sleep(100)


# ============================================================
#  MAIN
# ============================================================


if __name__ == "__main__":
    print("=" * 50)
    print("  PLACAR NEURON — Voz + HTML + Arduino")
    print("=" * 50)


    conectar_arduino()


    threading.Thread(target=iniciar_flask, daemon=True).start()
    time.sleep(1)
    print(f"\n[INFO] Abra o navegador em: http://localhost:5000\n")


    try:
        iniciar_vosk()
    except KeyboardInterrupt:
        print("\n[INFO] Encerrando.")
    finally:
        if arduino and arduino.is_open:
            arduino.close()