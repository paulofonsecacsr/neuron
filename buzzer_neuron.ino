int buzzer = 8;
int padrao_sonoro;

void setup() {
  pinMode(buzzer, OUTPUT);
  
  // Cria uma aleatoriedade real lendo um pino vazio
  randomSeed(analogRead(0)); 
}

void loop() {
  delay(300000); 
  
  padrao_sonoro = random(1, 3); 
  
  if (padrao_sonoro == 1) {
    // PADRÃO 1: Intervalado
    for (int i = 0; i < 5; i++) {
      digitalWrite(buzzer, HIGH);
      delay(200);
      digitalWrite(buzzer, LOW);
      delay(1800);
    }
  } 
  else {
    // PADRÃO 2: Contínuo
    for (int i = 0; i < 75; i++) {
      digitalWrite(buzzer, HIGH);
      delay(100);
      digitalWrite(buzzer, LOW);
      delay(100);
    }
  }
}