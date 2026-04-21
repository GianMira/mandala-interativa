# Mandala Interativa

Mandala generativa controlada pela mão via webcam. Usa MediaPipe para detectar os movimentos da mão em tempo real e Pygame para desenhar.

- Mover a mão → move a mandala
- Pinça (polegar + indicador) → zoom
- Girar a palma → gira as camadas em sentidos opostos
- Movimento rápido → dispara partículas coloridas
- Duas mãos → duas mandalas independentes
- Tecla `D` → desfoque de fundo (efeito Zoom/Teams)

[Ver o vídeo no YouTube](https://youtu.be/OD_0D74rvpk)

---

## Requisitos

- Python 3.11 (recomendado — 3.12+ pode ter incompatibilidades com MediaPipe)
- Webcam (embutida ou USB)
- ~200 MB de espaço em disco (dependências + modelos)

Os modelos de detecção de mão (~16 MB) são baixados automaticamente na primeira execução.

---

## Instalação

### Windows

1. Baixe e instale o Python 3.11 em [python.org](https://www.python.org/downloads/). Marque a opção **"Add Python to PATH"** durante a instalação.

2. Abra o PowerShell na pasta do projeto:
   ```
   cd mandala-interativa
   ```

3. Crie e ative o ambiente virtual:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
   O prompt deve mostrar `(venv)` na frente.

4. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

5. Execute:
   ```
   python mandala-interativa.py
   ```

---

### Linux (Ubuntu / Debian)

1. Instale o Python 3.11:
   ```
   sudo apt update
   sudo apt install python3.11 python3.11-venv python3-pip
   ```

2. Crie e ative o ambiente virtual:
   ```
   python3.11 -m venv venv
   source venv/bin/activate
   ```

3. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

4. Execute:
   ```
   python mandala-interativa.py
   ```

---

### macOS

1. Instale o Homebrew se ainda não tiver: [brew.sh](https://brew.sh)

2. Instale o Python 3.11:
   ```
   brew install python@3.11
   ```

3. Crie e ative o ambiente virtual:
   ```
   python3.11 -m venv venv
   source venv/bin/activate
   ```

4. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

5. Execute:
   ```
   python mandala-interativa.py
   ```

   Na primeira execução o macOS pode pedir permissão de câmera — aceite em **Ajustes do Sistema → Privacidade e Segurança → Câmera**.

---

## Descobrindo o ID da câmera

Por padrão o script usa `CAMERA_ID = 0`, que é sempre a câmera embutida ou a única câmera conectada. Se você tiver mais de uma câmera (USB, virtual, celular via DroidCam, etc.), rode:

```
python camera_find.py
```

Exemplo de saída no Windows:
```
[0] Integrated Webcam          →  640x480
[1] DroidCam (celular)         →  1280x720
[2] HD Pro Webcam              →  1280x720
```

No Linux as câmeras aparecem como `/dev/video0`, `/dev/video1`, etc. O índice do OpenCV corresponde ao número no final.

Depois de identificar o índice, edite a linha no início do script:
```python
CAMERA_ID = 2   # troque pelo número correto
```

---

## Controles pelo teclado

| Tecla | Função |
|---|---|
| `1` a `5` | Paleta de cores: Terra, Âmbar, Oceano, Ametista, Névoa |
| `+` / `-` | Aumenta ou diminui o número de pétalas (6 a 32) |
| `B` | Alterna o blend mode: Normal ↔ Aditivo (efeito neon) |
| `C` | Liga/desliga a imagem da câmera no fundo |
| `D` | Liga/desliga o desfoque de fundo (estilo Zoom) |
| `[` / `]` | Câmera mais escura / mais clara — só Windows |
| `F` | Tela cheia |
| `S` | Salva screenshot (`screenshot_AAAAMMDD_HHMMSS.png`) |
| `R` | Inicia/para gravação de vídeo (`mandala_AAAAMMDD_HHMMSS.mp4`) |
| `Q` ou `ESC` | Sair |

---

## Problemas comuns

### A câmera não abre / tela preta

- Verifique se outra aplicação está usando a câmera (Zoom, Teams, OBS, etc.)
- Tente outro valor de `CAMERA_ID` (0, 1, 2...) — rode `camera_find.py` para listar
- No Linux, verifique se o usuário tem acesso ao dispositivo:
  ```
  sudo usermod -aG video $USER
  ```
  Faça logout e login novamente após o comando.
- No Linux, instale as ferramentas de câmera se necessário:
  ```
  sudo apt install v4l-utils
  v4l2-ctl --list-devices
  ```

### Erro ao instalar o MediaPipe no Python 3.12+

O MediaPipe pode não ter suporte a versões mais recentes do Python. Use o Python 3.11:
```
python3.11 -m venv venv
```

### FPS baixo com o desfoque ativado

O desfoque de fundo é pesado para o processador. Para melhorar:

1. Pressione `D` para desligar o desfoque — a detecção de mão continua funcionando
2. Edite o script e reduza a resolução da câmera:
   ```python
   W, H = 960, 540   # em vez de 1280, 720
   ```
3. Reduza a intensidade do desfoque:
   ```python
   BLUR_KERNEL = 31   # em vez de 55 (deve ser ímpar)
   ```

### Gravação de vídeo não funciona no Linux ou macOS

O codec `mp4v` pode exigir o FFmpeg instalado:
- Linux: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`

### Erro `ModuleNotFoundError: No module named 'mediapipe'`

O ambiente virtual não está ativado. Ative antes de rodar:
- Windows: `venv\Scripts\activate`
- Linux/macOS: `source venv/bin/activate`

### A mão é detectada mas a mandala não aparece

Certifique-se de que a palma está voltada para a câmera e bem iluminada. O MediaPipe funciona melhor com fundo contrastante e luz frontal.

---

## Compatibilidade por sistema

| Funcionalidade | Windows | Linux | macOS |
|---|---|---|---|
| Detecção de mão | ✓ | ✓ | ✓ |
| Desfoque de fundo | ✓ | ✓ | ✓ |
| Gravação MP4 | ✓ | ✓ * | ✓ * |
| Controle de exposição `[ ]` | ✓ | — | — |
| Câmera embutida | ✓ | ✓ | ✓ |
| Câmera USB / virtual | ✓ | ✓ | ✓ |

\* Requer FFmpeg instalado no sistema.

---

## Dependências

| Pacote | Versão mínima | Função |
|---|---|---|
| opencv-python | 4.8.0 | Captura de câmera e processamento de imagem |
| mediapipe | 0.10.0 | Detecção de mão e segmentação de pessoa |
| pygame | 2.5.0 | Janela, desenho e eventos de teclado |
| numpy | 1.24.0 | Operações em arrays de imagem |
