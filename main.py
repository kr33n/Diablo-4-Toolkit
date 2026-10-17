import tkinter as tk
from core.autokey import AutoKeyService
from core.camera_patcher import CameraPatcherService
from gui.app_window import DiabloToolkitApp
import multiprocessing

def main():
    # Inicializa os serviços (Model/Business)
    autokey_service = AutoKeyService()
    camera_service = CameraPatcherService()

    # Inicializa a Interface Gráfica (View/Controller)
    root = tk.Tk()
    app = DiabloToolkitApp(root, autokey_service, camera_service)
    
    root.mainloop()

if __name__ == "__main__":
    multiprocessing.freeze_support() # OBRIGATÓRIO PARA MULTIPROCESSAMENTO NO WINDOWS
    main()