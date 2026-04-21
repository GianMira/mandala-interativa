"""
Mandala Interativa — MediaPipe + Pygame
========================================
Mandala generativa controlada pela mão via webcam.
Inclui desfoque de fundo (estilo Zoom) e controle de exposição da câmera.

DEPENDÊNCIAS:
  pip install opencv-python mediapipe pygame numpy

CÂMERA (CAMERA_ID, linha ~45):
  0  = câmera padrão / embutida
  1, 2, ... = câmeras adicionais (USB, virtual, etc.)
  Para descobrir o índice certo rode: python camera_find.py

COMPATIBILIDADE:
  Windows  — completo (exposição manual via DSHOW)
  Linux    — funciona; exposição automática ([ ] não têm efeito)
  macOS    — funciona; exposição automática ([ ] não têm efeito)

CONTROLES:
  Gesto pinça (polegar+indicador)  → zoom da mandala
  Mover a mão                      → move a mandala
  Girar a palma                    → gira as camadas
  2 mãos                           → duas mandalas independentes

  [1-5]   paleta de cores
  [+/-]   pétalas (+2 / -2)
  [B]     blend: Normal ↔ Aditivo
  [C]     câmera no fundo on/off
  [D]     desfoque de fundo on/off  (estilo Zoom/Teams)
  [[]     câmera mais escura        (só Windows/DSHOW)
  []]     câmera mais clara         (só Windows/DSHOW)
  [F]     fullscreen
  [S]     salvar screenshot
  [R]     iniciar/parar gravação MP4
  [Q/ESC] sair
"""

import platform

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import pygame
import math
import numpy as np
import time
import os
import sys
import urllib.request
import threading

# ─────────────────────────────────────────────
#  CONFIGURAÇÕES — edite aqui se necessário
# ─────────────────────────────────────────────
W, H = 1280, 720          # resolução da janela
FPS  = 60

# Índice da câmera: 0 = padrão/embutida, 1/2/... = câmeras extras.
# Se a imagem não aparecer, troque o valor. Rode camera_find.py para listar.
CAMERA_ID = 0

MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
MODEL_PATH = "hand_landmarker.task"

SEG_URL  = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter_landscape/float16/latest/selfie_segmenter_landscape.tflite"
SEG_PATH = "selfie_segmenter_landscape.tflite"

# Intensidade do desfoque de fundo (tecla D). Valor ímpar, ex: 21, 35, 55, 75.
BLUR_KERNEL = 55

IS_WINDOWS = platform.system() == "Windows"

# ─────────────────────────────────────────────
#  PALETAS DE CORES
# ─────────────────────────────────────────────
PALETTES = {
    # tons médios, dessaturados — harmônicos com fundo escuro
    1: [(180,140,100),(100,140,180),(160,180,120),(200,170,130),(120,150,170)],  # terra
    2: [(190,100, 80),(190,150, 70),(160,120, 80),(210,160,110),(150, 90, 70)],  # âmbar
    3: [( 80,130,170),( 90,160,180),(110,150,160),(130,170,190),( 70,120,150)],  # oceano
    4: [(150,110,170),(130, 90,150),(160,130,180),(140,100,160),(170,140,190)],  # ametista
    5: [(160,160,150),(140,150,140),(170,160,150),(150,160,170),(130,140,130)],  # névoa
}
STYLE_NAMES = {1:"Terra", 2:"Âmbar", 3:"Oceano", 4:"Ametista", 5:"Névoa"}

# ─────────────────────────────────────────────
#  CLASSE MANDALA
# ─────────────────────────────────────────────
class Mandala:
    def __init__(self, cx, cy, palette_id=1):
        self.cx = float(cx)
        self.cy = float(cy)
        self.radius = 162.0  # 90% do raio original
        self.angle = 0.0
        self.spin_speed = 0.012
        self.petals = 12
        self.palette_id = palette_id
        self.trail = []
        self.ray_trails = [[] for _ in range(8)]
        self.prev_cx = float(cx)
        self.prev_cy = float(cy)
        self.velocity = 0.0
        self.sector_colors = {}   # (layer, petal_idx) -> [color_rgb, alpha]
        self.palm_angle = 0.0
        self.layer_angles = [0.0, 0.0, 0.0, 0.0]
        # raio individual por pétala: (layer, petal_idx) -> fator atual [0.8..1.2]
        self.petal_radii  = {}
        # alvo suave para cada pétala: (layer, petal_idx) -> fator alvo
        self.petal_targets = {}
        self.prev_palm_delta = 0.0

    def update(self, target_x, target_y, target_radius, petals, palm_ang=None):
        self.cx += (target_x - self.cx) * 0.12
        self.cy += (target_y - self.cy) * 0.12
        self.radius += (target_radius - self.radius) * 0.10
        self.petals = petals

        dx = self.cx - self.prev_cx
        dy = self.cy - self.prev_cy
        self.velocity = math.hypot(dx, dy)
        self.spin_speed = 0.008 + min(self.velocity * 0.004, 0.08)

        self.trail.append((int(self.cx), int(self.cy), self.radius * 0.15))
        if len(self.trail) > 25:
            self.trail.pop(0)

        # acende setores aleatórios com o movimento (excluindo layer 0 = maior disco)
        if self.velocity > 1.5:
            colors = PALETTES[self.palette_id]
            for layer in range(1, 4):   # começa em 1 — layer 0 não recebe setor
                n_p = self.petals + layer * 3
                # poucos setores: 1 ou 2 no máximo por frame por camada
                n_new = 1 if self.velocity < 6 else 2
                for _ in range(n_new):
                    idx = np.random.randint(n_p)
                    key = (layer, idx)
                    color = colors[np.random.randint(len(colors))]
                    alpha = np.random.randint(70, 170)
                    self.sector_colors[key] = [color, alpha]

        # fade dos setores
        to_del = [k for k, v in self.sector_colors.items() if v[1] <= 0]
        for k in to_del:
            del self.sector_colors[k]
        for v in self.sector_colors.values():
            v[1] -= 3

        self.prev_cx = self.cx
        self.prev_cy = self.cy

        # spin base muito lento (quase parado — a palma é o motor principal)
        base_drift = self.spin_speed * 0.15

        # rotação da palma: calcula delta real entre frames
        if palm_ang is not None:
            diff = palm_ang - self.palm_angle
            # normaliza para [-pi, pi]
            while diff >  math.pi: diff -= 2*math.pi
            while diff < -math.pi: diff += 2*math.pi
            # suavização leve (0.25 = resposta rápida mas não nervosa)
            palm_delta = diff * 0.25
            self.palm_angle += palm_delta
        else:
            palm_delta = 0.0

        # 4 camadas: [0,2] seguem a palma / [1,3] vão no sentido contrário
        sensitivities = [1.0, 1.0, 0.8, 0.8]
        signs         = [  1,  -1,    1,  -1]
        for li in range(4):
            palm_contrib = palm_delta * sensitivities[li] * signs[li]
            drift        = base_drift * signs[li]
            self.layer_angles[li] += palm_contrib + drift

        # ── raios dinâmicos das pétalas ──
        # quando há rotação da palma, sorteia novas pétalas para mudar raio
        if abs(palm_delta) > 0.008:
            for layer in range(4):
                n_p = self.petals + layer * 3
                # sorteia 1-3 pétalas por camada para ganhar novo alvo
                n_new = np.random.randint(1, 4)
                for _ in range(n_new):
                    idx = np.random.randint(n_p)
                    key = (layer, idx)
                    # alvo entre 0.80 e 1.20 do raio base
                    self.petal_targets[key] = np.random.uniform(0.80, 1.20)

        # interpola suavemente todos os raios ativos em direção ao alvo
        to_del = []
        for key, target in self.petal_targets.items():
            current = self.petal_radii.get(key, 1.0)
            new_r   = current + (target - current) * 0.06  # lerp lento
            self.petal_radii[key] = new_r
            # remove quando chegou perto o suficiente do alvo
            if abs(new_r - target) < 0.005:
                to_del.append(key)
        for k in to_del:
            del self.petal_targets[k]
            # volta suavemente para 1.0 após atingir o alvo
            self.petal_targets[k] = 1.0  # reconverge para base

        self.prev_palm_delta = palm_delta
        self.angle += base_drift

    def draw(self, surface):
        colors = PALETTES[self.palette_id]
        cx, cy = int(self.cx), int(self.cy)
        r = int(self.radius)

        # ── rastro do centro (círculos que somem) ──
        for i, (tx, ty, tr) in enumerate(self.trail):
            age = i / max(len(self.trail), 1)
            rad = max(1, int(tr * age))
            color = colors[i % len(colors)]
            fc = tuple(int(c * age) for c in color)
            if rad > 0 and any(v > 0 for v in fc):
                pygame.draw.circle(surface, fc, (tx, ty), rad)

        # ── camadas de mandala ──
        for layer in range(4):
            layer_r = int(r * (1 - layer * 0.18))
            if layer_r < 10:
                continue
            layer_angle = self.layer_angles[layer]
            line_color  = colors[layer % len(colors)]
            n_petals    = self.petals + layer * 3
            sector_a    = (2 * math.pi / n_petals)

            for i in range(n_petals):
                a  = layer_angle + sector_a * i
                a2 = a + sector_a

                # ── setor colorido com alpha (polígono preenchido) ──
                key = (layer, i)
                if key in self.sector_colors:
                    sc, sa = self.sector_colors[key]
                    sa = max(0, min(255, sa))
                    inner_f = 0.15
                    outer_f = 1.0
                    steps = 12
                    pts = []
                    for s in range(steps + 1):
                        ang = a + (a2 - a) * s / steps
                        pts.append((cx + layer_r * outer_f * math.cos(ang),
                                    cy + layer_r * outer_f * math.sin(ang)))
                    for s in range(steps, -1, -1):
                        ang = a + (a2 - a) * s / steps
                        pts.append((cx + layer_r * inner_f * math.cos(ang),
                                    cy + layer_r * inner_f * math.sin(ang)))
                    if len(pts) >= 3:
                        # desenha em surface com alpha usando Surface temporária
                        poly_surf = pygame.Surface((r * 3, r * 3), pygame.SRCALPHA)
                        offset = r
                        shifted = [(px - cx + offset, py - cy + offset) for px, py in pts]
                        pygame.draw.polygon(poly_surf, (*sc, sa), shifted)
                        surface.blit(poly_surf, (cx - offset, cy - offset))

                # fator de raio individual desta pétala (80%..120%)
                pr = self.petal_radii.get((layer, i), 1.0)
                # clamp para nunca ultrapassar o anel externo nem o interno
                pr = max(0.80, min(1.20, pr))
                petal_r = layer_r * pr

                # linha principal da pétala (comprimento dinâmico)
                x1 = cx + int(layer_r * 0.15 * math.cos(a))
                y1 = cy + int(layer_r * 0.15 * math.sin(a))
                x2 = cx + int(petal_r * math.cos(a))
                y2 = cy + int(petal_r * math.sin(a))
                pygame.draw.aaline(surface, line_color, (x1, y1), (x2, y2))

                # círculo na ponta (acompanha o raio dinâmico)
                tip_x = cx + int(petal_r * math.cos(a))
                tip_y = cy + int(petal_r * math.sin(a))
                pygame.draw.circle(surface, line_color, (tip_x, tip_y), max(1, 4 - layer))

                # pétala secundária (entre pétalas, tb com raio dinâmico)
                amid = a + sector_a * 0.5
                pr2  = self.petal_radii.get((layer, (i+1) % n_petals), 1.0)
                pr2  = max(0.80, min(1.20, pr2))
                xm   = cx + int(layer_r * 0.6 * pr2 * math.cos(amid))
                ym   = cy + int(layer_r * 0.6 * pr2 * math.sin(amid))
                pygame.draw.aaline(surface, line_color, (cx, cy), (xm, ym))

            # anel externo (aalines aproximado com pontos)
            pts_ring = [(cx + int(layer_r * math.cos(2*math.pi*i/80)),
                         cy + int(layer_r * math.sin(2*math.pi*i/80))) for i in range(81)]
            pygame.draw.aalines(surface, line_color, True, pts_ring[:80])

            # anel interno tracejado
            inner_r = int(layer_r * 0.45)
            dash_n  = n_petals * 2
            for i in range(0, dash_n, 2):
                a1d = layer_angle + (2 * math.pi / dash_n) * i
                a2d = layer_angle + (2 * math.pi / dash_n) * (i + 1)
                pygame.draw.aaline(surface, line_color,
                    (cx + int(inner_r * math.cos(a1d)), cy + int(inner_r * math.sin(a1d))),
                    (cx + int(inner_r * math.cos(a2d)), cy + int(inner_r * math.sin(a2d))))

        # ── núcleo ──
        pygame.draw.circle(surface, colors[0], (cx, cy), max(4, r // 16))
        pygame.draw.circle(surface, (0, 0, 0),  (cx, cy), max(2, r // 24))

        # ── satélites ──
        for i in range(6):
            a  = self.angle * 1.7 + (2 * math.pi / 6) * i
            sr = int(r * 1.15)
            sx = cx + int(sr * math.cos(a))
            sy = cy + int(sr * math.sin(a))
            dot   = max(2, r // 20)
            color = colors[(i + 2) % len(colors)]
            pygame.draw.circle(surface, color, (sx, sy), dot)
            pygame.draw.circle(surface, color, (sx, sy), dot * 2, 1)

        # ── raios externos com círculo na ponta + rastro de círculos ──
        for i in range(8):
            a   = self.angle * 0.5 + (2 * math.pi / 8) * i
            rx1 = cx + int(r * 1.05 * math.cos(a))
            ry1 = cy + int(r * 1.05 * math.sin(a))
            rx2 = cx + int(r * 1.45 * math.cos(a))
            ry2 = cy + int(r * 1.45 * math.sin(a))
            color = colors[i % len(colors)]

            # linha do raio (antialiased)
            pygame.draw.aaline(surface, color, (rx1, ry1), (rx2, ry2))

            # círculo na ponta — sem rastro
            tip_r = max(3, r // 18)
            pygame.draw.circle(surface, color, (rx2, ry2), tip_r)
            pygame.draw.circle(surface, (0, 0, 0), (rx2, ry2), max(1, tip_r - 2))


# ─────────────────────────────────────────────
#  PARTÍCULAS
# ─────────────────────────────────────────────
class Particle:
    def __init__(self, x, y, color):
        self.x, self.y = float(x), float(y)
        angle = np.random.uniform(0, 2*math.pi)
        speed = np.random.uniform(1, 4)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = 1.0
        self.decay = np.random.uniform(0.02, 0.05)
        self.color = color
        self.size = np.random.randint(2, 6)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.05
        self.life -= self.decay
        self.vx *= 0.98

    def draw(self, surface):
        if self.life > 0:
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.size)


# ─────────────────────────────────────────────
#  UTILITÁRIOS
# ─────────────────────────────────────────────
def landmark_pinch(lm_list, w, h):
    dx = (lm_list[4].x - lm_list[8].x) * w
    dy = (lm_list[4].y - lm_list[8].y) * h
    return math.hypot(dx, dy)

def landmark_center(lm_list, w, h):
    return int((1.0 - lm_list[9].x) * w), int(lm_list[9].y * h)

def palm_rotation(lm_list):
    """
    Estima rotação da palma calculando o ângulo do vetor
    do pulso (lm 0) até a base do dedo médio (lm 9).
    Retorna ângulo em radianos. Invertido em X por causa do espelho.
    """
    dx = -(lm_list[9].x - lm_list[0].x)   # inverte X
    dy =   lm_list[9].y - lm_list[0].y
    return math.atan2(dy, dx)

def draw_hud(surface, small_font, style_id, petals, additive, fps, hand_count,
             blur_bg=False, exposure=-6, recording=False, rec_secs=0):
    rec_label  = f"● REC {rec_secs:.0f}s  [R] parar" if recording else "[R] gravar MP4"
    rec_col    = (255, 60, 60) if recording else (160, 160, 160)
    blur_label = "Foco: ON  [D]" if blur_bg else "Foco: off [D]"
    blur_col   = (120, 220, 120) if blur_bg else (120, 120, 120)
    if IS_WINDOWS:
        exp_bar = "".join("█" if exposure == v else "░" for v in range(-8, -3))
        exp_str = f"Luz: {exp_bar}  [[ ]]"
        exp_col = (220, 200, 100)
    else:
        exp_str = "Luz: auto  ([ ] só no Windows)"
        exp_col = (120, 120, 120)
    lines = [
        (f"Estilo: {STYLE_NAMES[style_id]}  [1-5]",           (200,200,200)),
        (f"Pétalas: {petals}  [+/-]",                          (200,200,200)),
        (f"Blend: {'Aditivo' if additive else 'Normal'}  [B]", (200,200,200)),
        (f"FPS: {fps:.0f}",                                    (200,200,200)),
        (f"Mãos: {hand_count}",                                (200,200,200)),
        (blur_label,                                            blur_col),
        (exp_str,                                               exp_col),
        ("",                                                 (0,0,0)),
        (rec_label,                                          rec_col),
        ("[C] câmera  [S] foto  [F] fullscreen  [Q] sair",  (100,100,100)),
    ]
    for i, (line, col) in enumerate(lines):
        surface.blit(small_font.render(line, True, col), (10, 10 + i * 18))

    # indicador vermelho piscante no canto superior direito
    if recording and int(time.time() * 2) % 2 == 0:
        pygame.draw.circle(surface, (255, 0, 0), (surface.get_width() - 20, 20), 8)


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Mandala Interativa")
    clock = pygame.time.Clock()
    small_font = pygame.font.SysFont("consolas", 14)
    fullscreen = False

    # Abre a câmera com o backend adequado ao sistema operacional.
    # Windows usa DirectShow (DSHOW) que permite controle de exposição manual.
    # Linux e macOS usam o backend padrão (V4L2 / AVFoundation).
    if IS_WINDOWS:
        cap = cv2.VideoCapture(CAMERA_ID, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    else:
        cap = cv2.VideoCapture(CAMERA_ID)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # Exposição manual (só tem efeito no Windows/DSHOW).
    # Faixa útil: -4 (muito claro) até -8 (muito escuro). Padrão: -6.
    exposure = -6
    if IS_WINDOWS:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)   # 1 = manual no DSHOW
        cap.set(cv2.CAP_PROP_EXPOSURE, exposure)

    CAM_W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    CAM_H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_real = cap.get(cv2.CAP_PROP_FPS)
    print(f"Sistema: {platform.system()} | Camera [{CAMERA_ID}]: {CAM_W}x{CAM_H} @ {fps_real:.0f}fps")

    # ── Thread de captura — mantém sempre o frame mais recente sem bloquear o loop ──
    latest_frame = {"bgr": None, "lock": threading.Lock()}

    def capture_thread():
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            with latest_frame["lock"]:
                latest_frame["bgr"] = frame

    t = threading.Thread(target=capture_thread, daemon=True)
    t.start()

    # espera o primeiro frame chegar
    import time as _t
    while True:
        with latest_frame["lock"]:
            if latest_frame["bgr"] is not None:
                break
        _t.sleep(0.05)
    print("Captura iniciada!")

    # MediaPipe Tasks API — hand landmarker
    if not os.path.exists(MODEL_PATH):
        print("Baixando modelo hand_landmarker.task (~15MB), aguarde...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Modelo pronto!")

    base_opts = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    lm_opts = mp_vision.HandLandmarkerOptions(
        base_options=base_opts,
        num_hands=2,
        min_hand_detection_confidence=0.65,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
        running_mode=mp_vision.RunningMode.IMAGE,
    )
    hand_landmarker = mp_vision.HandLandmarker.create_from_options(lm_opts)

    # MediaPipe Tasks API — selfie segmenter (para blur de fundo)
    if not os.path.exists(SEG_PATH):
        print("Baixando modelo selfie_segmenter (~1MB), aguarde...")
        urllib.request.urlretrieve(SEG_URL, SEG_PATH)
        print("Segmentador pronto!")

    seg_opts = mp_vision.ImageSegmenterOptions(
        base_options=mp_python.BaseOptions(model_asset_path=SEG_PATH),
        running_mode=mp_vision.RunningMode.IMAGE,
        output_confidence_masks=True,
    )
    segmenter = mp_vision.ImageSegmenter.create_from_options(seg_opts)

    mandalas   = []
    particles  = []
    style_id   = 1
    petals     = 12
    additive   = True
    show_cam   = True
    blur_bg    = False
    last_spawn = time.time()
    overlay    = pygame.Surface((W, H), pygame.SRCALPHA)

    # gravação de vídeo — acumula frames com timestamps reais
    recording      = False
    rec_frames     = []      # lista de frames BGR
    rec_times      = []      # timestamp real de cada frame
    rec_start      = 0.0
    rec_fname      = ""

    running = True
    while running:
        clock.tick(FPS)
        fps = clock.get_fps()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE): running = False
                elif event.key == pygame.K_1: style_id = 1
                elif event.key == pygame.K_2: style_id = 2
                elif event.key == pygame.K_3: style_id = 3
                elif event.key == pygame.K_4: style_id = 4
                elif event.key == pygame.K_5: style_id = 5
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS): petals = min(petals+2, 32)
                elif event.key == pygame.K_MINUS: petals = max(petals-2, 6)
                elif event.key == pygame.K_b: additive = not additive
                elif event.key == pygame.K_c: show_cam = not show_cam
                elif event.key == pygame.K_d: blur_bg = not blur_bg
                elif event.key == pygame.K_LEFTBRACKET and IS_WINDOWS:
                    exposure = max(exposure - 1, -8)
                    cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
                    print(f"Exposição: {exposure}")
                elif event.key == pygame.K_RIGHTBRACKET and IS_WINDOWS:
                    exposure = min(exposure + 1, -4)
                    cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
                    print(f"Exposição: {exposure}")
                elif event.key == pygame.K_f:
                    fullscreen = not fullscreen
                    screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN if fullscreen else 0)
                elif event.key == pygame.K_s:
                    fname = f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
                    pygame.image.save(screen, fname)
                    print(f"Screenshot: {fname}")
                elif event.key == pygame.K_r:
                    if not recording:
                        rec_fname  = f"mandala_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
                        rec_frames = []
                        rec_times  = []
                        rec_start  = time.time()
                        recording  = True
                        print(f"● Gravando: {rec_fname}")
                    else:
                        recording = False
                        # monta o vídeo com o FPS real medido
                        if len(rec_frames) > 1:
                            total_t = rec_times[-1] - rec_times[0]
                            real_fps = (len(rec_frames) - 1) / max(total_t, 0.001)
                            real_fps = round(max(10.0, min(real_fps, 60.0)), 2)
                            print(f"■ Finalizando: {len(rec_frames)} frames @ {real_fps:.1f}fps reais...")
                            h_out, w_out = rec_frames[0].shape[:2]
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            vw = cv2.VideoWriter(rec_fname, fourcc, real_fps, (w_out, h_out))
                            for fr in rec_frames:
                                vw.write(fr)
                            vw.release()
                            print(f"✓ Salvo: {rec_fname}")
                        rec_frames = []
                        rec_times  = []

        # pega frame mais recente da thread (sem bloquear)
        with latest_frame["lock"]:
            if latest_frame["bgr"] is None:
                continue
            frame = latest_frame["bgr"].copy()

        cam_frame_bgr = frame.copy()          # BGR original para gravação
        frame = cv2.flip(frame, 1)            # espelha para exibição
        # redimensiona para janela (alivia MediaPipe e GPU)
        frame_small = cv2.resize(frame, (W, H))
        rgb = cv2.cvtColor(frame_small, cv2.COLOR_BGR2RGB)

        # ── desfoque de fundo (efeito Zoom) ──
        if blur_bg:
            mp_seg    = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            seg_res   = segmenter.segment(mp_seg)
            # confidence_masks[0] = máscara da pessoa (float32, 0..1)
            person_mask = seg_res.confidence_masks[0].numpy_view()
            # suaviza bordas da máscara para transição natural
            person_mask = cv2.GaussianBlur(person_mask, (21, 21), 0)
            person_3ch  = np.stack([person_mask] * 3, axis=-1)
            blurred_rgb = cv2.GaussianBlur(rgb, (BLUR_KERNEL, BLUR_KERNEL), 0)
            rgb = (rgb * person_3ch + blurred_rgb * (1.0 - person_3ch)).astype(np.uint8)

        if show_cam:
            dark = (rgb.astype(np.float32) * 0.35).astype(np.uint8)
            screen.blit(pygame.surfarray.make_surface(np.rot90(dark)), (0, 0))
        else:
            screen.fill((5, 5, 10))

        # detecção — usa frame redimensionado (mais rápido para o MediaPipe)
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        detection = hand_landmarker.detect(mp_image)

        hand_count = 0
        if detection.hand_landmarks:
            hand_count = len(detection.hand_landmarks)
            for idx, lm_list in enumerate(detection.hand_landmarks):
                hx, hy = landmark_center(lm_list, W, H)
                pinch  = landmark_pinch(lm_list, W, H)
                radius = int(np.clip(pinch * 0.9, 70, 230))

                while len(mandalas) <= idx:
                    mandalas.append(Mandala(hx, hy, palette_id=style_id))

                mandalas[idx].palette_id = style_id
                p_ang = palm_rotation(lm_list)
                mandalas[idx].update(hx, hy, radius, petals, palm_ang=p_ang)

                now = time.time()
                if mandalas[idx].velocity > 8 and now - last_spawn > 0.05:
                    for _ in range(4):
                        c = PALETTES[style_id][np.random.randint(len(PALETTES[style_id]))]
                        particles.append(Particle(hx, hy, c))
                    last_spawn = now

        # mandalas somem junto com as mãos
        while len(mandalas) > hand_count:
            mandalas.pop()

        overlay.fill((0, 0, 0, 0))
        for m in mandalas:
            m.draw(overlay)

        if additive:
            screen.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)
        else:
            screen.blit(overlay, (0, 0))

        particles = [p for p in particles if p.life > 0]
        for p in particles:
            p.update()
            p.draw(screen)

        rec_secs = (time.time() - rec_start) if recording else 0
        draw_hud(screen, small_font, style_id, petals, additive, fps, hand_count,
                 blur_bg=blur_bg, exposure=exposure, recording=recording, rec_secs=rec_secs)

        if hand_count == 0:
            msg = small_font.render("↑  mostre a palma da mão", True, (60, 60, 60))
            screen.blit(msg, (W//2 - msg.get_width()//2, H - 30))

        pygame.display.flip()

        # captura frame para buffer (timestamp real)
        if recording:
            px  = pygame.surfarray.array3d(screen)
            px  = np.transpose(px, (1, 0, 2))
            bgr = cv2.cvtColor(px, cv2.COLOR_RGB2BGR)
            rec_frames.append(bgr)
            rec_times.append(time.time())

    # salva gravação se ainda ativa ao fechar
    if recording and len(rec_frames) > 1:
        total_t  = rec_times[-1] - rec_times[0]
        real_fps = (len(rec_frames) - 1) / max(total_t, 0.001)
        real_fps = round(max(10.0, min(real_fps, 60.0)), 2)
        print(f"■ Salvando gravação: {len(rec_frames)} frames @ {real_fps:.1f}fps...")
        h_out, w_out = rec_frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(rec_fname, fourcc, real_fps, (w_out, h_out))
        for fr in rec_frames:
            vw.write(fr)
        vw.release()
        print(f"✓ Salvo: {rec_fname}")
    cap.release()
    hand_landmarker.close()
    segmenter.close()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()