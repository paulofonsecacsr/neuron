"""
PLACAR NEURON — Voz + HTML + Arduino + IA

Este script é o coração do sistema. Ele orquestra o microfone (Vosk), 
o hardware (Arduino), a interface visual (Flask) e o cérebro (Gemini).
"""

# ============================================================
#  BIBLIOTECAS NATIVAS DO PYTHON (Já vêm instaladas)
# ============================================================
import json           # Para ler e gravar dados estruturados (carrega os enigmas e monta o dicionário de voz)
import threading      # Permite rodar tarefas simultâneas (ex: o servidor Web e o microfone funcionam ao mesmo tempo sem travar)
import time           # Usado para criar pausas controladas (delays) no sistema
import unicodedata    # Ferramenta de texto usada para arrancar os acentos das palavras (ex: transforma "próxima" em "proxima")
import os             # Interage com o sistema operacional (usado aqui para mandar comandos de limpar a tela)
import logging        # Controla os registros do sistema (usado para calar a boca do servidor Flask no terminal)
import getpass        # Esconde a senha/chave digitada no terminal, garantindo privacidade
import sys            # Acessa funções profundas do terminal (usado para forçar a limpeza visual da tela do VS Code)
import warnings       # Gerenciador de alertas do Python (usado para ocultar avisos chatos de atualização)

# ============================================================
#  BIBLIOTECAS EXTERNAS (Precisam ser instaladas via pip)
# ============================================================
import serial         # (pyserial) Faz a comunicação via cabo USB com o hardware do Arduino
import sounddevice as sd # Acessa a placa de som e captura o áudio do microfone do computador em tempo real
import vosk           # Motor de reconhecimento de voz offline (Speech-to-Text) que escuta e entende o jogador
from flask import Flask, jsonify, send_file, send_from_directory # Cria o servidor Web local para exibir as perguntas na tela HTML
import google.generativeai as genai # Biblioteca oficial do Google para conversar com a Inteligência Artificial (Gemini)

# Silencia os logs e textos de configuração do motor do Vosk no terminal
vosk.SetLogLevel(-1)

# Oculta o aviso de depreciação de versão da biblioteca do Google
warnings.filterwarnings("ignore")


# =========================================================
#  UTILIDADE: LIMPEZA ABSOLUTA DE TERMINAL
# =========================================================
def limpar_tela():
    """
    Função blindada que garante que o terminal fique limpo.
    Resolve o bug do VS Code onde a tela apenas "rola" para baixo.
    """
    # 1. Tenta limpar usando o comando padrão do Windows (cls) ou Mac/Linux (clear)
    os.system('cls' if os.name == 'nt' else 'clear')
    
    # 2. Usa um código ANSI de baixo nível para esvaziar a memória visual do terminal e jogar o cursor pro topo
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()


# ============================================================
#  INICIALIZAÇÃO E CHAVE DA IA (ONBOARDING)
# ============================================================

limpar_tela()
print("=" * 55)
print("  INICIALIZAÇÃO DO SISTEMA — PLACAR NEURON")
print("=" * 55)
print(" Para ativar a inteligência artificial, precisamos da")
print(" chave da API. (Sua digitação ficará invisível)\n")

# O input fica invisível graças ao getpass
CHAVE_API = getpass.getpass(" Cole sua chave API do Gemini e aperte Enter: ").strip()

# Trava de segurança: se o usuário der Enter vazio, o programa morre
if not CHAVE_API:
    print("\n[ERRO] Nenhuma chave fornecida. Encerrando o sistema.")
    exit()

try:
    # Injeta a chave na biblioteca do Google e prepara o modelo mais rápido
    genai.configure(api_key=CHAVE_API)
    modelo_ia = genai.GenerativeModel('gemini-1.5-flash-latest')
except Exception as e:
    print(f"\n[ERRO] Falha ao configurar o Gemini: {e}")
    exit()

# Tela falsa de carregamento para feedback visual
limpar_tela()
print("=" * 55)
print("  CARREGANDO PLACAR NEURON...")
print("=" * 55)
print(" [OK] Inteligência Artificial conectada.")


# ============================================================
#  CONFIGURAÇÕES DE HARDWARE E REDE
# ============================================================

MODEL_PATH  = "vosk-model-small-pt-0.3" # Pasta onde está o cérebro offline de voz
SERIAL_PORT = "COM3"                    # Porta USB onde o Arduino está espetado
BAUD_RATE   = 9600                      # Velocidade de comunicação com o Arduino
SAMPLERATE  = 16000                     # Qualidade do áudio do microfone (16kHz é o padrão do Vosk)
FLASK_PORT  = 5000                      # Porta de rede onde a tela HTML vai rodar


# ============================================================
#  BANCO DE DADOS (CARREGA ENIGMAS)
# ============================================================

# Abre o arquivo de texto JSON e converte para um dicionário Python
with open("enigmas.json", encoding="utf-8") as f:
    ENIGMAS = json.load(f)


# ============================================================
#  MEMÓRIA DO JOGO E DICIONÁRIOS DE COMANDOS
# ============================================================

# O 'estado' é o cérebro da partida atual. Guarda em qual pergunta estamos, qual tela exibir, etc.
estado = {
    "enigma_index":      0,
    "tela":              "pergunta",
    "total":             len(ENIGMAS),
    "feedback":          None,
    "feedback_contador": 0,
    "ultima_acao":       "Sistema pronto. Aguardando comando..."
}

# Dicionário de navegação: A Chave é o que o jogador fala, o Valor é o que o programa faz
COMANDOS_ENIGMA = {
    "pergunta seguinte": "proximo",
    "enigma seguinte":   "proximo",
    "seguinte":          "proximo",
    "mostrar resposta":  "resposta",
    "revelar resposta":  "resposta",
    "mostrar pergunta":  "pergunta",
    "voltar":            "anterior",
    "enigma anterior":   "anterior",
}

# Dicionário do Arduino: A Chave é o que se fala, o Valor é a letra que vai pro USB acender o LED
COMANDOS_ARDUINO = {
    "ponto pulso vermelho": 'R', "ponto pulso verde": 'G', "ponto pulso azul": 'B', "ponto pulso amarelo": 'Y',
    "dois pontos pulso vermelho": 'Q', "dois pontos pulso verde": 'H', "dois pontos pulso azul": 'C', "dois pontos pulso amarelo": 'Z',
    "menos ponto pulso vermelho": 'r', "menos ponto pulso verde": 'g', "menos ponto pulso azul": 'b', "menos ponto pulso amarelo": 'y',
    "zerar pulso vermelho": 'w', "zerar pulso verde": 'h', "zerar pulso azul": 'c', "zerar pulso amarelo": 'z',
    "zerar tudo": 'X',
}

# Palavras de ruído que o sistema descarta automaticamente ao avaliar a resposta de um enigma
IGNORAR = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na",
    "por", "para", "com", "que", "e", "é", "eu", "não"
}


# =========================================================
#  INTERFACE DE USUÁRIO (DASHBOARD FIXO)
# =========================================================

def atualizar_painel(mensagem_acao=""):
    """
    Sempre que algo importante acontece, essa função é chamada.
    Ela apaga a tela inteira e redesenha o placar atualizado, 
    dando a sensação de um "aplicativo de painel estático".
    """
    if mensagem_acao:
        estado["ultima_acao"] = mensagem_acao
        
    limpar_tela()
    print("=" * 55)
    print("  PLACAR NEURON — Painel de Controle")
    print("=" * 55)
    print(f"  Enigma Atual : {estado['enigma_index'] + 1} de {estado['total']}")
    print(f"  Última Ação  : {estado['ultima_acao']}")
    print("  Microfone    : [ LIGADO ] Escutando comandos...")
    print("=" * 55)
    print(f"  Painel Web   : http://localhost:{FLASK_PORT}")
    print("  (Pressione Ctrl+C para encerrar o sistema)\n")


# =========================================================
#  FUNÇÃO DE INTELIGÊNCIA ARTIFICIAL (CORREÇÃO DE VOZ)
# =========================================================

def corrigir_comando_com_ia(texto_bruto_vosk, resposta_atual_enigma=""):
    """
    Pega o texto cru que o microfone ouviu e tenta encaixar em um dos comandos válidos.
    Se a fala foi perfeita, nem gasta internet. Se a fala veio torta, a IA conserta.
    """
    texto_bruto_vosk = texto_bruto_vosk.lower().strip()

    # Ignora se foi só um barulho vazio do ambiente
    if not texto_bruto_vosk or texto_bruto_vosk == "[unk]":
        return ""

    # =====================================================
    # ATALHO DE PERFORMANCE (BYPASS)
    # Se o texto falado for idêntico a algum comando da lista, aprova direto.
    # Isso zera a latência e poupa a cota de uso da IA.
    # =====================================================
    if texto_bruto_vosk in COMANDOS_ENIGMA.keys() or texto_bruto_vosk in COMANDOS_ARDUINO.keys():
        return texto_bruto_vosk
        
    # Função interna rápida para arrancar acentos e testar se o cara acertou o enigma
    def limpar_acento(txt):
        return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn').lower().strip()
    
    # Verifica se a pessoa falou a resposta do enigma exatamente como está escrita
    if texto_bruto_vosk == limpar_acento(resposta_atual_enigma) or texto_bruto_vosk == resposta_atual_enigma.lower().strip():
        return resposta_atual_enigma

    # =====================================================
    # ACIONAMENTO DA IA (Só cai aqui se o Vosk engasgou)
    # =====================================================
    chaves_enigma = ", ".join([f"'{k}'" for k in COMANDOS_ENIGMA.keys()])
    chaves_arduino = ", ".join([f"'{k}'" for k in COMANDOS_ARDUINO.keys()])

    # Prompt ditatorial proibindo a IA de inventar comandos novos
    prompt = f"""
    Você é um classificador algorítmico rigoroso. Não converse, não explique.
    BANCO DE DADOS: {chaves_enigma}, {chaves_arduino}, '{resposta_atual_enigma}'
    Texto com erro: '{texto_bruto_vosk}'
    Regra: Devolva EXATAMENTE E APENAS uma chave do banco de dados que corresponda à intenção. É proibido misturar chaves. Se não houver relação, devolva: ignorar
    """

    try:
        resposta = modelo_ia.generate_content(prompt)
        resultado = resposta.text.strip().lower().replace("'", "").replace('"', '')
        # Se a IA julgar que não tem nada a ver com o jogo, retorna vazio
        return "" if resultado == "ignorar" else resultado
    except Exception as e:
        # Em caso de falha de internet, devolve o que o Vosk ouviu mesmo
        return texto_bruto_vosk


# ============================================================
#  ARDUINO E HARDWARE
# ============================================================

arduino = None

def conectar_arduino():
    """Tenta abrir a porta USB para conversar com os LEDs"""
    global arduino
    try:
        arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(1) # Dá um tempinho pro chip do Arduino reiniciar e estabilizar
        print(f" [OK] Arduino detectado na porta {SERIAL_PORT}.")
    except Exception:
        print(" [AVISO] Arduino não detectado. Iniciando em modo offline.")


# ============================================================
#  LÓGICA PRINCIPAL DO JOGO (AVALIAÇÃO DOS TEXTOS)
# ============================================================

def limpar_feedback():
    """Limpa o aviso de 'ERRO' da tela HTML após alguns segundos"""
    estado["feedback"] = None
    atualizar_painel()

def processar_texto(texto):
    """
    Recebe o texto limpo da IA e toma uma decisão no jogo 
    (mudar tela, mandar letra pro Arduino ou validar resposta do enigma).
    """
    texto = texto.lower().strip()

    # 1. Verifica se foi pedido para mudar de tela ou de pergunta
    for frase, acao in COMANDOS_ENIGMA.items():
        if frase in texto:
            estado["feedback"] = None
            executar_acao_enigma(acao)
            return

    # 2. Verifica se foi pedido para alterar o placar de LEDs
    for frase, cmd in COMANDOS_ARDUINO.items():
        if frase in texto:
            if arduino and arduino.is_open:
                arduino.write(cmd.encode()) # Envia a letra pelo cabo USB
                atualizar_painel(f"Sinal do painel enviado (Código: {cmd})")
            else:
                atualizar_painel(f"Comando ignorado: Arduino desconectado ({cmd})")
            return

    # 3. Trava de segurança: O jogador só pode dar a resposta se estiver na tela da Pergunta
    if estado["tela"] != "pergunta":
        return

    # 4. Busca qual é o gabarito do enigma atual na memória
    idx_atual = estado["enigma_index"]
    resposta_correta = ENIGMAS[idx_atual]["resposta"].lower().strip()

    # 5. Verifica Acerto
    if resposta_correta in texto:
        estado["feedback"] = None
        estado["tela"] = "resposta"
        atualizar_painel(f"ACERTO! Resposta correta validada.")
        return

    # 6. Verifica Erro (Remove as palavras pequenas para não dar erro por causa de um 'o' ou 'a')
    palavras = [p for p in texto.split() if p not in IGNORAR and len(p) > 2]
    if palavras:
        estado["feedback"] = "erro"
        estado["feedback_contador"] += 1
        atualizar_painel(f"Resposta incorreta ou ruído: '{texto}'")
        # Inicia um cronômetro escondido que limpa o aviso vermelho da tela após 8 segundos
        threading.Timer(8.0, limpar_feedback).start()


def executar_acao_enigma(acao):
    """Executa a matemática de avançar ou voltar as páginas do jogo"""
    idx   = estado["enigma_index"]
    total = estado["total"]

    if acao == "proximo":
        if idx < total - 1:
            estado["enigma_index"] += 1
            estado["tela"] = "pergunta"
            atualizar_painel(f"Avançou para o Enigma {estado['enigma_index'] + 1}")
        else:
            atualizar_painel("Aviso: Já estamos no último enigma.")

    elif acao == "anterior":
        if idx > 0:
            estado["enigma_index"] -= 1
            estado["tela"] = "pergunta"
            atualizar_painel(f"Voltou para o Enigma {estado['enigma_index'] + 1}")
        else:
            atualizar_painel("Aviso: Já estamos no primeiro enigma.")

    elif acao == "resposta":
        estado["tela"] = "resposta"
        atualizar_painel("Tela atualizada para: Mostrar Resposta")

    elif acao == "pergunta":
        estado["tela"] = "pergunta"
        atualizar_painel("Tela atualizada para: Mostrar Pergunta")


# ============================================================
#  FLASK (SERVIDOR WEB LOCAL)
# ============================================================

# Conjunto de regras agressivas para silenciar qualquer log que o Flask tente imprimir
os.environ['WERKZEUG_RUN_MAIN'] = 'true'
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
cli = sys.modules.get('flask.cli', None)
if cli:
    cli.show_server_banner = lambda *x: None

app = Flask(__name__)

# Rota principal (O que aparece quando o cara digita http://localhost:5000)
@app.route("/")
def index():
    return send_file("perguntas.html") # Entrega o arquivo visual HTML

# Entrega a imagem da estampa para o HTML poder renderizá-la
@app.route("/Estampa_Neuron.png")
def estampa():
    return send_from_directory(".", "Estampa_Neuron.png")

# O HTML consulta essa rota várias vezes por segundo para saber se algo mudou
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

def iniciar_flask():
    """Roda o servidor Web na porta configurada, de forma invisível"""
    app.run(port=FLASK_PORT, debug=False, use_reloader=False)


# ============================================================
#  MICROFONE (VOSK) E MULTITHREADING
# ============================================================

def fluxo_ia_e_processamento(texto_bruto):
    """
    Função que roda numa Thread separada.
    Leva o texto pra IA arrumar e depois envia pro jogo.
    Se não fosse separada, o áudio picotaria durante a lentidão da internet.
    """
    idx_atual = estado["enigma_index"]
    resposta_esperada = ENIGMAS[idx_atual]["resposta"].lower().strip()
    
    comando_revisado = corrigir_comando_com_ia(texto_bruto, resposta_esperada)
    
    if comando_revisado:
        processar_texto(comando_revisado)


def iniciar_vosk():
    """Inicia o motor acústico que rouba o microfone do computador e fica escutando"""
    print(" [Aguarde] Carregando o modelo acústico...")
    model = vosk.Model(MODEL_PATH)
    
    # Prepara o dicionário de palavras restrito para o Vosk focar na escuta correta
    def limpar_palavra(texto):
        texto_sem_acento = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
        return texto_sem_acento.lower().strip()
    
    vocabulario = set(["[unk]", "sim", "nao", "dica"])
    for cmd in COMANDOS_ENIGMA.keys(): vocabulario.add(limpar_palavra(cmd))
    for cmd in COMANDOS_ARDUINO.keys(): vocabulario.add(limpar_palavra(cmd))
    for enigma in ENIGMAS: vocabulario.add(limpar_palavra(enigma["resposta"]))
        
    grammar_json = json.dumps(list(vocabulario))
    
    # Inicia o reconhecedor focado em 16kHz
    rec = vosk.KaldiRecognizer(model, SAMPLERATE, grammar_json)

    # Quando chegar aqui, tudo carregou. Limpa a tela e exibe o Painel!
    atualizar_painel()

    def callback(indata, frames, time_info, status):
        """Função que o microfone aciona repetidamente sempre que entra som novo"""
        if rec.AcceptWaveform(bytes(indata)):
            resultado = json.loads(rec.Result())
            texto_bruto = resultado.get("text", "").strip()
            
            # Se captou alguma fala, delega pra IA numa trilha separada
            if texto_bruto:
                threading.Thread(target=fluxo_ia_e_processamento, args=(texto_bruto,), daemon=True).start()

    # Liga a escuta contínua do microfone sem bloquear o código
    with sd.RawInputStream(samplerate=SAMPLERATE, blocksize=8000,
                           dtype="int16", channels=1, callback=callback):
        while True:
            sd.sleep(100) # Mantém o loop vivo infinitamente


# ============================================================
#  GATILHO DE PARTIDA (MAIN)
# ============================================================

# Se este script for executado diretamente, este bloco será o primeiro a rodar
if __name__ == "__main__":
    
    # 1. Tenta ligar os LEDs
    conectar_arduino()
    print(" [OK] Servidor Web preparado.")
    
    # 2. Inicia o site em segundo plano (O uso de daemon=True faz a thread morrer se o app fechar)
    threading.Thread(target=iniciar_flask, daemon=True).start()

    # 3. Inicia o microfone e prende o sistema aqui
    try:
        iniciar_vosk()
    
    # Se o usuário apertar Ctrl+C, cai neste bloco para encerrar bonito
    except KeyboardInterrupt:
        limpar_tela()
        print("\n=" * 55)
        print("  SISTEMA ENCERRADO COM SUCESSO. ATÉ LOGO!")
        print("=" * 55 + "\n")
    
    # Independente de ter dado erro ou fechado bonito, desliga a porta USB
    finally:
        if arduino and arduino.is_open:
            arduino.close()
