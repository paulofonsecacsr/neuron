"""
PLACAR NEURON — Voz + HTML + Arduino
Reconhecimento de voz: faster-whisper (local/offline) com VAD
Validação de resposta: múltipla escolha A/B/C/D
"""


import json
import queue
import threading
import time

import numpy as np
import serial
import sounddevice as sd
from faster_whisper import WhisperModel
from flask import Flask, jsonify, send_file, send_from_directory


# ============================================================
#  CONFIGURAÇÕES
# ============================================================


WHISPER_MODEL = "small"     # "small" (rápido) ou "medium" (mais preciso, exige mais CPU)
WHISPER_DEVICE = "cupu"      # "cpu" ou "cuda" se tiver placa de vídeo NVIDIA
COMPUTE_TYPE  = "int8"      # int8 é leve e roda bem em CPU comum
SERIAL_PORT   = "COM8"
BAUD_RATE     = 9600
SAMPLERATE    = 16000
FLASK_PORT    = 5000

# Parâmetros do detector de fala (VAD caseiro por volume)
# Com blocksize=4000, cada bloco dura ~0.25s.
SILENCIO_LIMIAR    = 250    # abaixo disso é silêncio (menor = pega bordas fracas da fala)
SILENCIO_BLOCOS    = 4      # nº de blocos de silêncio para encerrar a fala (~1.0s)
MIN_BLOCOS_FALA    = 2      # ignora ruídos muito curtos
PRE_ROLL_BLOCOS    = 3      # blocos de silêncio guardados ANTES da fala (evita cortar o início)
BLOCKSIZE          = 4000   # tamanho do bloco de áudio (~0.25s a 16kHz)


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
    "ponto vermelho":  'R',
    "ponto verde":     'G',
    "ponto azul":      'B',
    "ponto amarelo":   'Y',
    # +2 pontos
    "dois pontos vermelho": 'Q', "2 pontos vermelho": 'Q',
    "dois pontos verde":    'H', "2 pontos verde":    'H',
    "dois pontos azul":     'C', "2 pontos azul":     'C',
    "dois pontos amarelo":  'Z', "2 pontos amarelo":  'Z',
    # -1 ponto
    "menos ponto vermelho": 'r',
    "menos ponto verde":    'g',
    "menos ponto azul":     'b',
    "menos ponto amarelo":  'y',
    # zerar time
    "zerar vermelho":  'w',
    "zerar verde":     'h',
    "zerar azul":      'c',
    "zerar amarelo":   'z',
    # zerar tudo
    "zerar tudo":            'X',
}


# Mapeia muitas formas de falar cada letra para a, b, c, d.
# As frases mais longas são testadas primeiro (mais específicas).
# Inclui erros comuns de transcrição do whisper (ex.: "litra" no lugar de "letra").
MAPA_LETRAS = {
    "resposta a": "a", "alternativa a": "a", "letra a": "a", "opção a": "a", "opcao a": "a",
    "resposta b": "b", "alternativa b": "b", "letra b": "b", "opção b": "b", "opcao b": "b",
    "resposta c": "c", "alternativa c": "c", "letra c": "c", "opção c": "c", "opcao c": "c",
    "resposta d": "d", "alternativa d": "d", "letra d": "d", "opção d": "d", "opcao d": "d",
    # variações de "letra" mal transcritas
    "litra a": "a", "lítra a": "a", "litra b": "b", "lítra b": "b",
    "litra c": "c", "lítra c": "c", "litra d": "d", "lítra d": "d",
    # letra pronunciada por extenso
    "letra á": "a", "letra bê": "b", "letra cê": "c", "letra dê": "d",
    "resposta bê": "b", "resposta cê": "c", "resposta dê": "d", "resposta á": "a",
    "bê": "b", "cê": "c", "sê": "c", "dê": "d",
}


def detectar_letra(texto):
    """Tenta extrair A, B, C ou D do texto falado. Retorna a letra minúscula ou None."""
    t = " " + texto.lower().strip() + " "  # padding ajuda a casar " a " isolado
    for frase in sorted(MAPA_LETRAS, key=len, reverse=True):
        if frase in t:
            return MAPA_LETRAS[frase]
    return None


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


    # 1) Comandos de navegação (frases mais longas primeiro, por segurança)
    for frase in sorted(COMANDOS_ENIGMA, key=len, reverse=True):
        if frase in texto:
            estado["feedback"] = None
            executar_acao_enigma(COMANDOS_ENIGMA[frase])
            return


    # 2) Comandos do Arduino
    #    Testa as frases MAIS LONGAS primeiro. Sem isso, "ponto pulso vermelho"
    #    casaria dentro de "menos ponto pulso vermelho" e enviaria +1 em vez de -1.
    for frase in sorted(COMANDOS_ARDUINO, key=len, reverse=True):
        if frase in texto:
            cmd = COMANDOS_ARDUINO[frase]
            if arduino and arduino.is_open:
                arduino.write(cmd.encode())
                print(f"[LED] Comando '{cmd}' enviado ao Arduino")
            else:
                print(f"[LED] Arduino desconectado — '{cmd}' ignorado")
            return


    # 3) Só verifica resposta se estiver na tela de pergunta
    if estado["tela"] != "pergunta":
        return


    # 4) Detecta a letra falada (A/B/C/D)
    letra = detectar_letra(texto)
    if letra is None:
        return  # não falou uma alternativa válida; ignora


    idx_atual = estado["enigma_index"]
    correta = ENIGMAS[idx_atual]["correta"].lower().strip()


    # 5) Verifica acerto
    if letra == correta:
        print(f"[ACERTO] Alternativa correta: '{letra.upper()}'")
        estado["feedback"] = None
        estado["tela"] = "resposta"
        return


    # 6) Resposta errada
    print(f"[ERRO] Alternativa errada: '{letra.upper()}' (correta: '{correta.upper()}')")
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
    correta = enigma["correta"]
    return jsonify({
        "enigma_index":      idx,
        "enigma_numero":     idx + 1,
        "total":             estado["total"],
        "tela":              estado["tela"],
        "pergunta":          enigma["pergunta"],
        "alternativas":      enigma["alternativas"],
        "correta":           correta,
        "resposta":          enigma["alternativas"][correta],  # texto da correta (compatibilidade)
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
#  FASTER-WHISPER (substitui o Vosk)
# ============================================================


def iniciar_whisper():
    print("[VOZ] Carregando modelo faster-whisper... (pode demorar na 1ª vez)")
    model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=COMPUTE_TYPE)
    print("[VOZ] Pronto! Fale agora. (Ctrl+C para sair)\n")


    fila_audio = queue.Queue()


    def callback(indata, frames, time_info, status):
        # Joga o áudio cru numa fila; o processamento acontece fora do callback
        fila_audio.put(bytes(indata))


    def transcrever(audio_bytes):
        # Converte int16 -> float32 normalizado, como o whisper espera
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = model.transcribe(
            audio,
            language="pt",
            vad_filter=True,
            beam_size=1,          # 1 = mais rápido; aumente para mais precisão
            # Dica de vocabulário: enviesa o reconhecimento para os comandos do jogo
            initial_prompt=(
                "Comandos do jogo: resposta A, resposta B, resposta C, resposta D. "
                "Próxima pergunta, enigma anterior, mostrar resposta. "
                "Ponto pulso vermelho, ponto pulso verde, ponto pulso azul, ponto pulso amarelo. "
                "Zerar vermelho, zerar verde, zerar azul, zerar amarelo, zerar tudo."
            ),
            condition_on_previous_text=False,  # evita arrastar contexto e inventar palavras
        )
        return " ".join(s.text for s in segments).strip()


    # ---- Captura com PRE-ROLL: guarda blocos antes da fala p/ não cortar o início ----
    from collections import deque

    buffer_fala = []
    blocos_silencio = 0
    falando = False
    pre_roll = deque(maxlen=PRE_ROLL_BLOCOS)   # memória curta dos últimos blocos de silêncio


    with sd.RawInputStream(samplerate=SAMPLERATE, blocksize=BLOCKSIZE,
                           dtype="int16", channels=1, callback=callback):
        while True:
            bloco = fila_audio.get()

            # Mede o volume do bloco para detectar fala/silêncio
            amostras = np.frombuffer(bloco, dtype=np.int16)
            volume = np.abs(amostras).mean()

            if volume >= SILENCIO_LIMIAR:
                if not falando:
                    # Início da fala: começa com os blocos de pre-roll (o "antes")
                    falando = True
                    buffer_fala = list(pre_roll)
                buffer_fala.append(bloco)
                blocos_silencio = 0
            else:
                if falando:
                    # Continua gravando durante o silêncio curto (preserva o fim da fala)
                    buffer_fala.append(bloco)
                    blocos_silencio += 1

                    if blocos_silencio >= SILENCIO_BLOCOS:
                        if len(buffer_fala) >= MIN_BLOCOS_FALA:
                            audio_completo = b"".join(buffer_fala)
                            texto = transcrever(audio_completo)
                            if texto:
                                processar_texto(texto)
                        buffer_fala = []
                        blocos_silencio = 0
                        falando = False
                else:
                    # Silêncio antes de qualquer fala: alimenta a memória de pre-roll
                    pre_roll.append(bloco)


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
        iniciar_whisper()
    except KeyboardInterrupt:
        print("\n[INFO] Encerrando.")
    finally:
        if arduino and arduino.is_open:
            arduino.close()
