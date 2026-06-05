<!-- EXEMPLOS PARA REFERÊNCIA -->
<!-- https://github.com/bearbob/pyle -->

<!-- # Título -->
# NEURON

<!-- ## Descrição -->
<!-- O que é o jogo -->
<!-- Com o que (linguagem) foi construído -->
<!-- Por que foi criado -->
<img src="logo_neuron.png" alt="Logo da Neuron" width="33%">

**Neuron** é um jogo de enigmas em tabuleiro físico controlado por sensor de voz, permitindo-lhe ser jogado por pessoas com deficiências motoras graves. Sua criação foi motivada por um projeto de primeiro período da faculdade CESAR School, o qual gerou forte interesse em nossa equipe de desenvolver algo único e acessível. Seu funcionamento é baseado em programação em C++ associada ao Arduino Mega, sensor de voz Vosk Model desenvolvido em Python, ambos conectados por meio da biblioteca PySerial, e o site com os enigmas do jogo desenvolvido em HTML, CSS e JavaScript.

## Características
* **Acessibilidade e Inclusão:** Controle do jogo realizado inteiramente por comandos de voz, garantindo a participação autônoma e integradora de pessoas com deficiências motoras graves.
* **Interface Digital:** Plataforma visual onde os enigmas são apresentados aos jogadores e onde a validação das respostas acontece.
* **Tabuleiro Físico:** Estrutura interativa que mapeia o progresso da partida e sinaliza de forma clara o posicionamento de cada competidor no mundo real.
* **Integração Físico-Digital:** Experiência híbrida onde a resolução de enigmas em uma interface digital gera avanços luminosos no tabuleiro físico em tempo real.
* **Dinâmica Desafiadora:** Enigmas complexos que exigem intuição e raciocínio lógico para serem desvendados.
* **Multijogador Competitivo:** Desenvolvido para partidas dinâmicas e emocionantes no formato "cada um por si", reunindo 4 jogadores.


## Componentes e Tecnologias
#### Hardware (Estrutura Física e Eletrônica)
* **Arduino Mega 2560:** Placa microcontroladora principal responsável por receber os comandos e controlar a iluminação.
* **Componentes Eletrônicos:** 20x Pin LEDs inseridos no tabuleiro (5x Vermelhos, 5x Verdes, 5x Azuis, 5x amarelos) e fiação correspondente (jumpers e resistores).
* **Estrutura Física:** Tabuleiro do jogo construído e cortado em MDF.

#### Software e Bibliotecas
* **Python:** Linguagem principal (back-end) utilizada para a lógica de validação dos enigmas e processamento de voz.
* **Modelo Vosk:** Ferramenta de reconhecimento de voz (Speech Recognition) em Python para capturar os comandos do jogador offline.
* **pySerial:** Biblioteca Python utilizada para estabelecer a comunicação serial e enviar comandos do computador para o Arduino.
* **C++ (Arduino IDE):** Linguagem utilizada para programar o Arduino Mega, interpretando os dados recebidos via porta serial e acionando os pinos dos LEDs correspondentes.

#### Interface Gráfica (Front-end)
* **HTML5:** Estrutura base da interface gráfica aberta no navegador do computador, onde os enigmas são apresentados aos jogadores.
* **CSS3:** Inserido diretamente no próprio arquivo HTML, é responsável pela estilização visual da interface web, garantindo um design imersivo e atraente para o ambiente do jogo.
* **JavaScript:** Lógica de interatividade na página web, responsável por gerir os eventos do utilizador e fazer a ponte de comunicação dinâmica com a validação em Python.

## Instrução de instalação
<!-- Montagem -->

## Instrução de uso
<!-- Como jogar -->

## Licença
<!-- Dar permissão para uso comercial ou educacional somente -->
