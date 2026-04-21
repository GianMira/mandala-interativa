"""
Lista todas as câmeras disponíveis com nome e resolução real.
Requer: pip install pygrabber
"""
import cv2

# Tenta listar nomes via pygrabber (Windows)
try:
    from pygrabber.dshow_graph import FilterGraph
    graph = FilterGraph()
    device_names = graph.get_input_devices()
    print("=== Câmeras detectadas (DirectShow) ===")
    for i, name in enumerate(device_names):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            print(f"  [{i}] {name}  →  {w}x{h}")
        else:
            print(f"  [{i}] {name}  →  (não abriu)")
except ImportError:
    print("pygrabber não instalado — mostrando só por índice.\n"
          "Para ver nomes: pip install pygrabber\n")
    print("=== Câmeras por índice ===")
    for i in range(6):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            print(f"  [{i}]  {w}x{h}")
        cap.release()
