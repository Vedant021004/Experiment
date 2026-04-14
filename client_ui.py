import tkinter as tk
import socket
import threading
import json
import time
import random

HOST = '127.0.0.1'
PORT = 65432

class TrafficUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Dining Philosophers: Traffic Gridlock Simulator")
        self.root.geometry("1000x750")
        self.root.configure(bg="#0b0c10")

        self.sim_state = {
            "mode": "none",
            "zones": {1: None, 2: None, 3: None, 4: None},
            "cars_completed": 0,
            "cars": {}
        }
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.auto_demo = False

        self.setup_ui()
        self.connect_to_server()

    def setup_ui(self):
        top_frame = tk.Frame(self.root, bg="#1f2833")
        top_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(top_frame, text="OS & AOA Mini-Project: The Dining Philosophers", font=("Helvetica", 16, "bold"), bg="#1f2833", fg="#66fcf1").pack()
        tk.Label(top_frame, text="Philosophers = Cars | Forks = Intersection Zones 1,2,3,4", font=("Helvetica", 10), bg="#1f2833", fg="#c5c6c7").pack()
        
        # Throughput Metric (Best Idea)
        self.score_lbl = tk.Label(top_frame, text="Cars Safely Crossed: 0", font=("Helvetica", 14, "bold"), bg="#1f2833", fg="#2ecc40")
        self.score_lbl.pack(pady=5)
        
        self.status_lbl = tk.Label(top_frame, text="Connecting to Server (CN Sockets)...", fg="yellow", bg="#1f2833")
        self.status_lbl.pack()

        main_frame = tk.Frame(self.root, bg="#0b0c10")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        self.canvas = tk.Canvas(main_frame, width=500, height=500, bg="#1a1e24", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, padx=10)

        ctrl_frame = tk.Frame(main_frame, bg="#0b0c10")
        ctrl_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        tk.Button(ctrl_frame, text="RESET SIMULATION SERVER", bg="#ffdb58", fg="black", font=("Arial", 10, "bold"), 
                  command=self.reset_sim).pack(pady=5, fill=tk.X)

        tk.Label(ctrl_frame, text="Algorithm Control Panel", font=("Helvetica", 14, "bold"), bg="#0b0c10", fg="#fff").pack(pady=10)

        mode_frame = tk.Frame(ctrl_frame, bg="#1f2833", padx=10, pady=10)
        mode_frame.pack(fill=tk.X, pady=5)

        self.mode_var = tk.StringVar(value="none")
        
        r1 = tk.Radiobutton(mode_frame, text="Unregulated System (Demonstrates Deadlock)", variable=self.mode_var, value="none", 
                            command=self.set_mode, bg="#1f2833", fg="white", selectcolor="#0b0c10")
        r1.pack(anchor="w")
        
        r2 = tk.Radiobutton(mode_frame, text="Deadlock Prevention (Dijkstra's Resource Hierarchy)", variable=self.mode_var, value="prevention", 
                            command=self.set_mode, bg="#1f2833", fg="white", selectcolor="#0b0c10")
        r2.pack(anchor="w")
        
        r3 = tk.Radiobutton(mode_frame, text="Deadlock Avoidance (Banker's Semaphore Arbitrator)", variable=self.mode_var, value="avoidance", 
                            command=self.set_mode, bg="#1f2833", fg="white", selectcolor="#0b0c10")
        r3.pack(anchor="w")

        r4 = tk.Radiobutton(mode_frame, text="Deadlock Detection & Resolution (Wait-For Graph Rollback)", variable=self.mode_var, value="resolution", 
                            command=self.set_mode, bg="#1f2833", fg="#ff4136", selectcolor="#0b0c10", font=("Arial", 10, "bold"))
        r4.pack(anchor="w")

        self.desc_lbl = tk.Label(ctrl_frame, text="Standard unmanaged resource allocation. Prone to cyclical wait and permanent deadlock conditions.", 
                                 bg="#0b0c10", fg="#ff851b", font=("Arial", 10, "italic"), wraplength=400, justify="left")
        self.desc_lbl.pack(pady=10)

        tk.Label(ctrl_frame, text="System Actuators (Process Spawners)", bg="#0b0c10", fg="#aaa").pack(pady=5)
        
        btn_frame = tk.Frame(ctrl_frame, bg="#0b0c10")
        btn_frame.pack()
        
        tk.Button(btn_frame, text="Spawn North", width=15, bg="#45a29e", fg="white", command=lambda: self.send_spawn("N")).grid(row=0, column=1, pady=5)
        tk.Button(btn_frame, text="Spawn West", width=15, bg="#45a29e", fg="white", command=lambda: self.send_spawn("W")).grid(row=1, column=0, padx=5)
        tk.Button(btn_frame, text="Spawn East", width=15, bg="#45a29e", fg="white", command=lambda: self.send_spawn("E")).grid(row=1, column=2, padx=5)
        tk.Button(btn_frame, text="Spawn South", width=15, bg="#45a29e", fg="white", command=lambda: self.send_spawn("S")).grid(row=2, column=1, pady=5)

        tk.Button(ctrl_frame, text="Force Gridlock (Spawn All 4)", bg="#b12b2b", fg="white", font=("Arial", 10, "bold"), 
                  command=self.spawn_all, pady=5).pack(pady=5, fill=tk.X)

        # Auto-Demo Button
        self.auto_btn = tk.Button(ctrl_frame, text="Start Auto-Demo Mode", bg="#2ecc40", fg="black", font=("Arial", 10, "bold"), 
                  command=self.toggle_auto_demo, pady=5)
        self.auto_btn.pack(pady=5, fill=tk.X)

        self.zone_labels = {}
        for z in range(1, 5):
            lbl = tk.Label(ctrl_frame, text=f"Fork {z}: Free", bg="#0b0c10", fg="#2ecc40", font=("Arial", 10))
            lbl.pack(anchor="w")
            self.zone_labels[z] = lbl

    def connect_to_server(self):
        def attempt_connection():
            while not self.connected:
                try:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.connect((HOST, PORT))
                    self.connected = True
                    self.status_lbl.config(text="Online (Connected via TCP Sockets)", fg="#2ecc40")
                    threading.Thread(target=self.receive_data, daemon=True).start()
                except Exception as e:
                    time.sleep(2)
        threading.Thread(target=attempt_connection, daemon=True).start()

    def receive_data(self):
        buffer = ""
        while self.connected:
            try:
                data = self.sock.recv(1024)
                if not data: break
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        self.sim_state = json.loads(line)
                        self.root.after(0, self.update_ui)
            except:
                break
        self.connected = False
        self.status_lbl.config(text="Offline (Server disconnected)", fg="red")
        self.connect_to_server()

    def send_spawn(self, direction):
        if self.connected:
            self.sock.sendall((json.dumps({"action": "spawn", "direction": direction}) + "\n").encode('utf-8'))

    def spawn_all(self):
        for d in ["N", "E", "S", "W"]:
            self.send_spawn(d)

    def set_mode(self):
        if self.connected:
            self.sock.sendall((json.dumps({"action": "set_mode", "value": self.mode_var.get()}) + "\n").encode('utf-8'))
        
        mode = self.mode_var.get()
        if mode == "none":
            self.desc_lbl.config(text="Standard unmanaged resource allocation. Prone to cyclical wait and permanent deadlock conditions.")
        elif mode == "prevention":
            self.desc_lbl.config(text="OS Concept: Deadlock Prevention. Enforces strict numeric ordering on resource requests to algorithmically guarantee no cyclical graphs.")
        elif mode == "avoidance":
            self.desc_lbl.config(text="OS Concept: Deadlock Avoidance. Utilizes a counting semaphore to dynamically ensure the system never enters an unsafe state.")
        elif mode == "resolution":
            self.desc_lbl.config(text="OS Concept: Deadlock Detection & Recovery. Run unregulated, but a background graph analyzer continuously detects circular waits and preempts (rolls back) processes.")

    def reset_sim(self):
        if self.connected:
            self.sock.sendall((json.dumps({"action": "reset"}) + "\n").encode('utf-8'))

    def toggle_auto_demo(self):
        self.auto_demo = not self.auto_demo
        if self.auto_demo:
            self.auto_btn.config(text="Stop Auto-Demo Mode", bg="#ff4136", fg="white")
            self.trigger_auto_spawn()
        else:
            self.auto_btn.config(text="Start Auto-Demo Mode", bg="#2ecc40", fg="black")

    def trigger_auto_spawn(self):
        if self.auto_demo and self.connected:
            d = random.choice(["N", "E", "S", "W"])
            self.send_spawn(d)
            # Randomly spawn every 0.5 to 1.5 seconds
            self.root.after(random.randint(500, 1500), self.trigger_auto_spawn)

    def update_ui(self):
        if self.mode_var.get() != self.sim_state["mode"]:
            self.mode_var.set(self.sim_state["mode"])
            self.set_mode()
            
        self.score_lbl.config(text=f"Cars Safely Crossed (Throughput): {self.sim_state.get('cars_completed', 0)}")
            
        for z in range(1, 5):
            owner = self.sim_state["zones"][str(z)]
            if owner:
                self.zone_labels[z].config(text=f"Fork {z}: Held by {owner}", fg="#ff4136")
            else:
                self.zone_labels[z].config(text=f"Fork {z}: Free", fg="#2ecc40")

        self.draw_canvas()

    def draw_canvas(self):
        self.canvas.delete("all")
        W, H = 500, 500
        cx, cy = W//2, H//2

        self.canvas.create_rectangle(cx-40, 0, cx+40, H, fill="#222", outline="")
        self.canvas.create_rectangle(0, cy-40, W, cy+40, fill="#222", outline="")
        
        self.canvas.create_line(cx, 0, cx, cy-40, fill="white", dash=(10, 10))
        self.canvas.create_line(cx, cy+40, cx, H, fill="white", dash=(10, 10))
        self.canvas.create_line(0, cy, cx-40, cy, fill="white", dash=(10, 10))
        self.canvas.create_line(cx+40, cy, W, cy, fill="white", dash=(10, 10))

        z_coords = {
            1: (cx-40, cy-40, cx, cy),
            2: (cx, cy-40, cx+40, cy),
            3: (cx, cy, cx+40, cy+40),
            4: (cx-40, cy, cx, cy+40)
        }

        for z in range(1, 5):
            x1, y1, x2, y2 = z_coords[z]
            owner = self.sim_state["zones"][str(z)]
            fill_color = "#441111" if owner else "#113311"
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline="white")
            self.canvas.create_text(x1+10, y1+10, text=f"F{z}", fill="white", font=("Arial", 10, "bold"))

        for cid, car in self.sim_state["cars"].items():
            self.draw_car(car, cx, cy, W, H)

    def draw_car(self, car, cx, cy, W, H):
        prog = car["progress"]
        d = car["direction"]
        cw, ch = 20, 30 
        lane_offset = 20
        
        if d == "N": 
            x = cx - lane_offset - cw//2
            y = (prog / 100) * H - ch
        elif d == "S": 
            x = cx + lane_offset - cw//2
            y = H - (prog / 100) * H 
        elif d == "E":
            x = W - (prog / 100) * W
            y = cy - lane_offset - cw//2
            cw, ch = 30, 20
        elif d == "W":
            x = (prog / 100) * W - cw
            y = cy + lane_offset - cw//2
            cw, ch = 30, 20

        color = "#66fcf1"
        if car["status"] in ["waiting", "waiting_middle"]:
            color = "#ff851b"
            
        self.canvas.create_rectangle(x, y, x+cw, y+ch, fill=color)
        
        tx, ty = x + cw//2, y + ch//2
        self.canvas.create_text(tx, ty, text=car["id"][:2], fill="black", font=("Arial", 8, "bold"))

        if car["waiting_for"]:
            self.canvas.create_text(tx, ty - 15, text=f"! Wait {car['waiting_for']}", fill="red", font=("Arial", 10, "bold"))
            
        self.canvas.create_text(tx, ty + 20, text=car.get("algo_detail",""), fill="yellow", font=("Arial", 7))

if __name__ == "__main__":
    root = tk.Tk()
    app = TrafficUI(root)
    root.mainloop()
