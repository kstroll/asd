import random
import string
from tkinter import filedialog
import soundfile as sf
import tkinter as tk
import customtkinter as ctk
import os
import sys
import torch
import warnings
import customtkinter as ctk
import http.server
import http.client
from urllib.parse import urlparse

# Константы
SID = 0
F0_PITCH = -20
F0_FILE = None
#F0_METHOD = 'crepe'
F0_METHOD = 'dio'
FILE_INDEX = r"models\pudge_ru_250epoch\added_IVF67_Flat_nprobe_1_rudga2_v2.index"
INDEX_RATE = 0.4
#CREPE_HOP_LENGTH = 512  # Примерный размер, подставьте нужный для вашего случая
CREPE_HOP_LENGTH = 128  # Примерный размер, подставьте нужный для вашего случая
PTH_FILE_PATH = r"./models/pudge_ru_250epoch/rudga2_e250_s1250.pth"
INDEX_FILE_PATH = r"./models/pudge_ru_250epoch/added_IVF67_Flat_nprobe_1_rudga2_v2.index"

now_dir = os.getcwd()
sys.path.append(now_dir)
tmp = os.path.join(now_dir, "TEMP")
os.makedirs(os.path.join(now_dir, "models"), exist_ok=True)
os.makedirs(os.path.join(now_dir, "output"), exist_ok=True)
os.environ["TEMP"] = tmp
warnings.filterwarnings("ignore")
torch.manual_seed(114514)

from vc_infer_pipeline import VC
from fairseq import checkpoint_utils
from scipy.io import wavfile
from my_utils import load_audio
from infer_pack.models import SynthesizerTrnMs256NSFsid, SynthesizerTrnMs256NSFsid_nono
from infer_pack.modelsv2 import SynthesizerTrnMs768NSFsid_nono, SynthesizerTrnMs768NSFsid
from multiprocessing import cpu_count
import threading
from time import sleep
from time import sleep
import traceback
import numpy as np
import subprocess
import zipfile
from config import Config


config = Config()



def extract_model_from_zip(zip_path, output_dir):
    # Extract the folder name from the zip file path
    folder_name = os.path.splitext(os.path.basename(zip_path))[0]

    # Create a folder with the same name as the zip file inside the output directory
    output_folder = os.path.join(output_dir, folder_name)
    os.makedirs(output_folder, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            if (member.endswith('.pth') and not (os.path.basename(member).startswith("G_") or os.path.basename(member).startswith("D_")) and zip_ref.getinfo(member).file_size < 200*(1024**2)) or (member.endswith('.index') and not (os.path.basename(member).startswith("trained"))):
                # Extract the file to the output folder
                zip_ref.extract(member, output_folder)

                # Move the file to the top level of the output folder
                file_path = os.path.join(output_folder, member)
                new_path = os.path.join(output_folder, os.path.basename(file_path))
                os.rename(file_path, new_path)

    print(f"Model files extracted to folder: {output_folder}")
    
    
def play_audio(file_path):
    if sys.platform == 'win32':
        audio_file = os.path.abspath(file_path)
        subprocess.call(['start', '', audio_file], shell=True)
    elif sys.platform == 'darwin':
        audio_file = 'path/to/audio/file.wav'
        subprocess.call(['open', audio_file])
    elif sys.platform == 'linux':
        audio_file = 'path/to/audio/file.wav'
        subprocess.call(['xdg-open', audio_file])

def get_full_path(path):
    return os.path.abspath(path)

hubert_model = None
device = config.device
print(device)
is_half = config.is_half

def load_hubert():
    global hubert_model
    models, _, _ = checkpoint_utils.load_model_ensemble_and_task(
        ["hubert_base.pt"],
        suffix="",
    )
    hubert_model = models[0]
    hubert_model = hubert_model.to(config.device)
    if is_half:
        hubert_model = hubert_model.half()
    else:
        hubert_model = hubert_model.float()
    hubert_model.eval()


def vc_single(
    input_audio,
    output_path,
    sid=SID,
    f0_up_key=F0_PITCH,
    f0_file=F0_FILE,
    f0_method=F0_METHOD,
    file_index=FILE_INDEX,
    index_rate=INDEX_RATE,
    crepe_hop_length=CREPE_HOP_LENGTH,
):
    global tgt_sr, net_g, vc, hubert_model
    if input_audio is None:
        return "You need to upload an audio", None
    f0_up_key = int(f0_up_key)
    try:
        audio = load_audio(input_audio, 16000)
        times = [0, 0, 0]
        if hubert_model == None:
            load_hubert()
        if_f0 = cpt.get("f0", 1)
        file_index = (
            file_index.strip(" ")
            .strip('"')
            .strip("\n")
            .strip('"')
            .strip(" ")
            .replace("trained", "added")
        )  # 防止小白写错，自动帮他替换掉
     
        audio_opt = vc.pipeline(
            hubert_model,
            net_g,
            sid,
            audio,
            times,
            f0_up_key,
            f0_method,
            file_index,
            # file_big_npy,
            index_rate,
            if_f0,
            version,
            crepe_hop_length,
            None,
        )
        print(
            "npy: ", times[0], "s, f0: ", times[1], "s, infer: ", times[2], "s", sep=""
        )

        if output_path is not None:
            sf.write(output_path, audio_opt, tgt_sr, format='WAV')

        return "Success", (tgt_sr, audio_opt)
    except:
        info = traceback.format_exc()
        print(info)
        return info, (None, None)


def vc_multi(
    sid,
    dir_path,
    opt_root,
    paths,
    f0_up_key,
    f0_method,
    file_index,
    index_rate,
):
    try:
        dir_path = (
            dir_path.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
        )  # 防止小白拷路径头尾带了空格和"和回车
        opt_root = opt_root.strip(" ").strip(
            '"').strip("\n").strip('"').strip(" ")
        os.makedirs(opt_root, exist_ok=True)
        try:
            if dir_path != "":
                paths = [os.path.join(dir_path, name)
                         for name in os.listdir(dir_path)]
            else:
                paths = [path.name for path in paths]
        except:
            traceback.print_exc()
            paths = [path.name for path in paths]
        infos = []
        for path in paths:
            info, opt = vc_single(
                sid,
                path,
                f0_up_key,
                None,
                f0_method,
                file_index,
                index_rate,
            )
            if info == "Success":
                try:
                    tgt_sr, audio_opt = opt
                    wavfile.write(
                        "%s/%s" % (opt_root, os.path.basename(path)
                                   ), tgt_sr, audio_opt
                    )
                except:
                    info = traceback.format_exc()
            infos.append("%s->%s" % (os.path.basename(path), info))
            yield "\n".join(infos)
        yield "\n".join(infos)
    except:
        yield traceback.format_exc()


# 一个选项卡全局只能有一个音色
def get_vc(weight_root, sid):
    global n_spk, tgt_sr, net_g, vc, cpt, version
    if sid == "" or sid == []:
        global hubert_model
        if hubert_model != None:  # 考虑到轮询, 需要加个判断看是否 sid 是由有模型切换到无模型的
            print("clean_empty_cache")
            del net_g, n_spk, vc, hubert_model, tgt_sr  # ,cpt
            hubert_model = net_g = n_spk = vc = hubert_model = tgt_sr = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            ###楼下不这么折腾清理不干净
            if_f0 = cpt.get("f0", 1)
            version = cpt.get("version", "v1")
            if version == "v1":
                if if_f0 == 1:
                    net_g = SynthesizerTrnMs256NSFsid(
                        *cpt["config"], is_half=config.is_half
                    )
                else:
                    net_g = SynthesizerTrnMs256NSFsid_nono(*cpt["config"])
            elif version == "v2":
                if if_f0 == 1:
                    net_g = SynthesizerTrnMs768NSFsid(
                        *cpt["config"], is_half=config.is_half
                    )
                else:
                    net_g = SynthesizerTrnMs768NSFsid_nono(*cpt["config"])
            del net_g, cpt
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            cpt = None
        return {"visible": False, "__type__": "update"}
    person = (weight_root)
    print("loading %s" % person)
    cpt = torch.load(person, map_location="cpu")
    tgt_sr = cpt["config"][-1]
    cpt["config"][-3] = cpt["weight"]["emb_g.weight"].shape[0]  # n_spk
    if_f0 = cpt.get("f0", 1)
    version = cpt.get("version", "v1")
    if version == "v1":
        if if_f0 == 1:
            net_g = SynthesizerTrnMs256NSFsid(*cpt["config"], is_half=config.is_half)
        else:
            net_g = SynthesizerTrnMs256NSFsid_nono(*cpt["config"])
    elif version == "v2":
        if if_f0 == 1:
            net_g = SynthesizerTrnMs768NSFsid(*cpt["config"], is_half=config.is_half)
        else:
            net_g = SynthesizerTrnMs768NSFsid_nono(*cpt["config"])
    del net_g.enc_q
    print(net_g.load_state_dict(cpt["weight"], strict=False))
    net_g.eval().to(config.device)
    if config.is_half:
        net_g = net_g.half()
    else:
        net_g = net_g.float()
    vc = VC(tgt_sr, config)
    n_spk = cpt["config"][-3]
    return {"visible": True, "maximum": n_spk, "__type__": "update"}


def clean():
    return {"value": "", "__type__": "update"}


def if_done(done, p):
    while 1:
        if p.poll() == None:
            sleep(0.5)
        else:
            break
    done[0] = True


def if_done_multi(done, ps):
    while 1:
        # poll==None代表进程未结束
        # 只要有一个进程未结束都不停
        flag = 1
        for p in ps:
            if p.poll() == None:
                flag = 0
                sleep(0.5)
                break
        if flag == 1:
            break
    done[0] = True


# window


def outputkey(length=5):
    # generate all possible characters
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=length))
# choose `length` characters randomly from the list and join them into a string

def refresh_model_list():
    global model_folders
    model_folders = [f for f in os.listdir(models_dir) if os.path.isdir(os.path.join(
    models_dir, f)) and any(f.endswith(".pth") for f in os.listdir(os.path.join(models_dir, f)))]
    model_list.configure(values=model_folders)
    model_list.update()

def browse_zip():
    global zip_file
    zip_file = filedialog.askopenfilename(
        initialdir=os.getcwd(),
        title="Select file",
        filetypes=(("zip files", "*.zip"), ("all files", "*.*")),
    )
    extract_model_from_zip(zip_file, models_dir)
    refresh_model_list()
    
def get_output_path(file_path):
    
    if not os.path.exists(file_path):
        # change the file extension to .wav
        
        return file_path  # File path does not exist, return as is

    # Split file path into directory, base filename, and extension
    dir_name, file_name = os.path.split(file_path)
    file_name, file_ext = os.path.splitext(file_name)

    # Initialize index to 1
    index = 1

    # Increment index until a new file path is found
    while True:
        new_file_name = f"{file_name}_RVC_{index}{file_ext}"
        new_file_path = os.path.join(dir_name, new_file_name)
        if not os.path.exists(new_file_path):
            # change the file extension to .wav
            new_file_path = os.path.splitext(new_file_path)[0] + ".wav"
            return new_file_path  # Found new file path, return it
        index += 1
    
def on_button_click():
    output_audio_frame.pack_forget()
    result_state.pack_forget()
    run_button.configure(state="disabled")

    # Get values from user input widgets
    sid = sid_entry.get()
    input_audio = input_audio_entry.get()
    f0_pitch = round(f0_pitch_entry.get())
    crepe_hop_length = round((crepe_hop_length_entry.get()) * 64)
    f0_file = None
    f0_method = f0_method_entry.get()
    file_index = file_index_entry.get()
    # file_big_npy = file_big_npy_entry.get()
    index_rate = round(index_rate_entry.get(),2)
    global output_file
    output_file = get_output_path(input_audio)
    print("sid: ", sid, "input_audio: ", input_audio, "f0_pitch: ", f0_pitch, "f0_file: ", f0_file, "f0_method: ", f0_method,
          "file_index: ", file_index, "file_big_npy: ", "index_rate: ", index_rate, "output_file: ", output_file)
    # Call the vc_single function with the user input values
    if model_loaded == True and os.path.isfile(input_audio):
        try:
            loading_frame.pack(padx=10, pady=10)
            loading_progress.start()
            
            result, audio_opt = vc_single(
                0, input_audio, f0_pitch, None, f0_method, file_index, index_rate,crepe_hop_length, output_file)
            # output_label.configure(text=result + "\n saved at" + output_file)
            print(os.path.join(output_file))
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
              print(output_file) 
              
              run_button.configure(state="enabled")
              message = result
              result_state.configure(text_color="green")
              last_output_file.configure(text=output_file)
              output_audio_frame.pack(padx=10, pady=10)
            else: 
              message = result
              result_state.configure(text_color="red")

        except Exception as e:
            print(e)
            message = "Voice conversion failed", e

    # Update the output label with the result
       # output_label.configure(text=result + "\n saved at" + output_file)

        run_button.configure(state="enabled")
    else:
        message = "Please select a model and input audio file"
        run_button.configure(state="enabled")
        result_state.configure(text_color="red")

    loading_progress.stop()
    loading_frame.pack_forget()
    result_state.pack(padx=10, pady=10, side="top")
    result_state.configure(text=message)


def browse_file():
    filepath = filedialog.askopenfilename (
        filetypes=[("Audio Files", "*.wav;*.mp3")])
    filepath = os.path.normpath(filepath)  # Normalize file path
    input_audio_entry.delete(0, tk.END)
    input_audio_entry.insert(0, filepath)



def start_processing():

    t = threading.Thread(target=on_button_click)
    t.start()


# Create tkinter window and widgets
root = ctk.CTk()
ctk.set_appearance_mode("dark")
root.title("RVC GUI")
# Get screen dimensions
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

# Set GUI dimensions as a percentage of screen size

gui_height = int(screen_height * 0.85)  # 80% of screen height
gui_dimensions = f"800x{gui_height}"

root.geometry(gui_dimensions)
root.resizable(False, True)

model_loaded = False


def selected_model(choice):
    file_index_entry.delete(0, ctk.END)
    model_dir = os.path.join(models_dir, choice)
    pth_files = [f for f in os.listdir(model_dir) if os.path.isfile(os.path.join(model_dir, f)) 
                 and f.endswith(".pth") and not (f.startswith("G_") or f.startswith("D_"))
                 and os.path.getsize(os.path.join(model_dir, f)) < 200*(1024**2)]
    
    if pth_files:
        global pth_file_path
        pth_file_path = os.path.join(model_dir, pth_files[0])
        npy_files = [f for f in os.listdir(model_dir) if os.path.isfile(os.path.join(model_dir, f)) 
                     and f.endswith(".index")]
        if npy_files:
            npy_files_dir = [os.path.join(model_dir, f) for f in npy_files]
            if len(npy_files_dir) == 1:
                index_file = npy_files_dir[0]
                print(f".pth file directory: {pth_file_path}")
                print(f".index file directory: {index_file}")
                file_index_entry.insert(0, os.path.normpath(index_file))
            else:
                print(f"Incomplete set of .index files found in {model_dir}")
        else:
            print(f"No .index files found in {model_dir}")
        get_vc(pth_file_path, 0)
        global model_loaded
        model_loaded = True
    else:
        print(f"No eligible .pth files found in {model_dir}")


def index_slider_event(value):
    index_rate_label.configure(
        text='Feature retrieval rate: %s' % round(value, 2))
   # print(value)


def pitch_slider_event(value):
    f0_pitch_label.configure(text='Pitch: %s' % round(value))
  #  print(value)
  
def crepe_hop_length_slider_event(value):
    crepe_hop_length_label.configure(text='crepe hop: %s' % round((value) * 64))
  #  print(value)


# hide crepe hop length slider if crepe is not selected
def crepe_hop_length_slider_visibility(value):
    if value == "crepe" or value == "crepe-tiny":
        crepe_hop_length_label.grid(row=2, column=0, padx=10, pady=5, )
        crepe_hop_length_entry.grid(row=2, column=1, padx=10, pady=5, )
    else:
        crepe_hop_length_label.grid_remove()
        crepe_hop_length_entry.grid_remove()

def update_config(selected):
    global device, is_half  # declare newconfig as a global variable
    if selected == "GPU":
        device = "cuda:0"
       # is_half = True
    else:
        if torch.backends.mps.is_available():
         device = "mps"
       #  is_half = False
        else: 
            device = "cpu"
            is_half = False

    config.device = device
    config.is_half = is_half
    

    if "pth_file_path" in globals():
        load_hubert()
        get_vc(pth_file_path, 0)

# "runtime\python.exe" main.py --pycmd "runtime\python.exe"
class MyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Получаем путь из запроса
        parsed_path = urlparse(self.path)
        
        # В зависимости от пути выполняем различные действия
        if parsed_path.path == "/sing":
            print("ETO SING")
            input_audio = r"C:\Users\moistv\ai\zxc.mp3"
            output_path = r"C:\Users\moistv\Desktop\test\smellsPudge.mp3"

            vc_single(input_audio, output_path)

            # Создаем подключение
            conn = http.client.HTTPConnection("localhost", 8900) 
            # Отправляем GET-запрос
            conn.request("GET", "/vtt")
            # Получаем ответ
            print("Сделали Голос пуджа отправляем на конвертацию в текст:")
            response = conn.getresponse()

            # Читаем и выводим содержимое ответа
            print("Статус:ответ", response.status)
            # Закрываем соединение
            conn.close()

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>SING</h1></body></html>")
        elif parsed_path.path == "/jump":
            print("eto jump")
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>play</h1></body></html>")
        else:
            print("ETO 404")
            print(parsed_path.path)
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>ddd</h1></body></html>")

def run_server():
    # Настройка порта и сервера
    PORT = 8890
    with http.server.HTTPServer(("", PORT), MyHandler) as httpd:
        print(f"Сервер запущен на http://localhost:{PORT}")
        httpd.serve_forever()

"""
server_thread = threading.Thread(target=run_server)
server_thread.daemon = True  # Устанавливаем поток как демонический, чтобы он завершился при завершении основного потока
server_thread.start()
"""
def cpu_choise():
    global device, is_half
    device = "cpu"
    is_half = False

    config.device = device
    config.is_half = is_half

if __name__ == "__main__":
    """
    crepy 
    hop 512
    float rate 0.4
    """
    global pth_file_path
    pth_file_path = PTH_FILE_PATH
    index_file = INDEX_FILE_PATH
    cpu_choise()
    get_vc(pth_file_path, 0)
    input_audio = r"C:\Users\moistv\ai\low.mp3"
    output_path = r"C:\Users\moistv\Desktop\test\lowRVC.mp3"
    vc_single(input_audio, output_path)
    #run_server()