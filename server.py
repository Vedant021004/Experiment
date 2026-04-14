import socket
import threading
import json
import time

zones = {1: threading.Lock(), 2: threading.Lock(), 3: threading.Lock(), 4: threading.Lock()}
zone_owners = {1: None, 2: None, 3: None, 4: None}
cars = {}
algorithm_mode = "none"
arbitrator_semaphore = threading.Semaphore(3)
client_sockets = []

current_generation = 0
cars_completed = 0

def reset_sim():
    global zone_owners, cars, zones, arbitrator_semaphore, current_generation, cars_completed
    current_generation += 1 
    zones = {1: threading.Lock(), 2: threading.Lock(), 3: threading.Lock(), 4: threading.Lock()}
    arbitrator_semaphore = threading.Semaphore(3)
    zone_owners = {1: None, 2: None, 3: None, 4: None}
    cars.clear()
    cars_completed = 0

def broadcast_state():
    while True:
        state = {
            "mode": algorithm_mode,
            "zones": zone_owners,
            "cars_completed": cars_completed,
            "cars": {k: v for k, v in cars.items()}
        }
        msg = json.dumps(state) + "\n"
        for c in client_sockets[:]:
            try:
                c.sendall(msg.encode('utf-8'))
            except:
                client_sockets.remove(c)
        time.sleep(0.02) 

def handle_car(car_id, direction, gen):
    if direction == "N": needs = [1, 4]
    elif direction == "E": needs = [2, 1]
    elif direction == "S": needs = [3, 2]
    elif direction == "W": needs = [4, 3]

    cars[car_id] = {
        "id": car_id, "direction": direction, 
        "progress": 0, "status": "arriving",
        "waiting_for": None, "acquired": [],
        "algo_detail": "",
        "preempt": False
    }
    car = cars[car_id]

    def move_to(target, step=1, delay=0.02):
        while car["progress"] < target:
            if current_generation != gen: return False
            
            my_num = int(car["id"].split('_')[0][1:])
            ahead_car = None
            closest_ahead = -1
            for other_id, other_car in cars.items():
                if other_car["direction"] == direction:
                    other_num = int(other_id.split('_')[0][1:])
                    if other_num < my_num and other_num > closest_ahead:
                        closest_ahead = other_num
                        ahead_car = other_car
            
            can_move = True
            if ahead_car:
                if ahead_car["progress"] - car["progress"] < 9:
                    can_move = False
                    
            if can_move:
                car["progress"] = min(target, car["progress"] + step)
                
            time.sleep(delay)
        return True

    if not move_to(25): return

    car["status"] = "waiting"

    global algorithm_mode
    req_order = needs
    if algorithm_mode == "prevention":
        req_order = sorted(needs)
        car["algo_detail"] = f"Rule: Must request F{req_order[0]} before F{req_order[1]}"
    elif algorithm_mode == "avoidance":
        car["algo_detail"] = "Rule: Wait for Arbitrator Token"
    elif algorithm_mode == "resolution":
        car["algo_detail"] = f"Rule: Grab F{needs[0]}, resolved dynamically if cycle detected"
    else:
        car["algo_detail"] = f"Rule: Grab F{needs[0]} blindly"

    def try_acquire(zone_id):
        while True:
            if current_generation != gen: return False
            if car.get("preempt", False): return False
            if zones[zone_id].acquire(timeout=0.2):
                return True

    finished_cleanly = False
    acquired_arbitrator = False
    
    try:
        while True:
            car["preempt"] = False
            try:
                if algorithm_mode == "avoidance":
                    car["waiting_for"] = "Token"
                    while True:
                        if current_generation != gen: return
                        if arbitrator_semaphore.acquire(timeout=0.2):
                            acquired_arbitrator = True
                            break
                    car["waiting_for"] = None
                    car["algo_detail"] = "Token acquired. Safe to enter."
                
                if algorithm_mode == "prevention":
                    # Dijkstra's method requires acquiring both forks in global order BEFORE proceeding
                    car["waiting_for"] = f"F{req_order[0]}"
                    if not try_acquire(req_order[0]): raise Exception("Preempted")
                    zone_owners[req_order[0]] = car_id
                    car["acquired"].append(req_order[0])

                    car["waiting_for"] = f"F{req_order[1]}"
                    if not try_acquire(req_order[1]): raise Exception("Preempted")
                    zone_owners[req_order[1]] = car_id
                    car["acquired"].append(req_order[1])
                    
                    car["waiting_for"] = None
                    car["status"] = "entering"
                    if not move_to(50): return
                    
                    car["status"] = "crossing"
                    if not move_to(75): return
                else:
                    # Standard local dynamic hold-and-wait
                    car["waiting_for"] = f"F{needs[0]}"
                    if not try_acquire(needs[0]): raise Exception("Preempted")
                    
                    zone_owners[needs[0]] = car_id
                    car["acquired"].append(needs[0])
                    car["waiting_for"] = None
                    car["status"] = "entering"
                    
                    if not move_to(50): return

                    car["waiting_for"] = f"F{needs[1]}"
                    car["status"] = "waiting_middle"
                    if not try_acquire(needs[1]): raise Exception("Preempted")
                    
                    zone_owners[needs[1]] = car_id
                    car["acquired"].append(needs[1])
                    car["waiting_for"] = None
                    car["status"] = "crossing"

                    if not move_to(75): return
                    
                finished_cleanly = True
                break
            
            except Exception as e:
                if str(e) == "Preempted":
                    car["algo_detail"] = "PREEMPTED: CYCLE DETECTED! Aborting process..."
                    for z in list(car["acquired"]):
                        zone_owners[z] = None
                        zones[z].release()
                        car["acquired"].remove(z)
                    if algorithm_mode == "avoidance" and acquired_arbitrator:
                        arbitrator_semaphore.release()
                        acquired_arbitrator = False
                        
                    # Terminating the preempted process cleanly resolving cycle overlaps
                    if car_id in cars:
                        del cars[car_id]
                    return
                else:
                    raise
    finally:
        if current_generation == gen:
            for z in list(car["acquired"]):
                zone_owners[z] = None
                zones[z].release()
                car["acquired"].remove(z)
                
            if algorithm_mode == "avoidance" and acquired_arbitrator:
                arbitrator_semaphore.release()
            
            car["status"] = "exiting"
            if move_to(100): pass

            if car_id in cars:
                del cars[car_id]
                
            if finished_cleanly:
                global cars_completed
                cars_completed += 1

def handle_client(conn, addr):
    client_sockets.append(conn)
    car_counter = 1
    with conn:
        buffer = ""
        while True:
            try:
                data = conn.recv(1024)
                if not data: break
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line: continue
                    msg = json.loads(line)
                    
                    if msg.get("action") == "spawn":
                        d = msg.get("direction")
                        cid = f"P{car_counter}_{d}"
                        car_counter += 1
                        threading.Thread(target=handle_car, args=(cid, d, current_generation), daemon=True).start()
                    elif msg.get("action") == "set_mode":
                        global algorithm_mode
                        algorithm_mode = msg.get("value")
                    elif msg.get("action") == "reset":
                        reset_sim()
            except:
                break
    if conn in client_sockets:
        client_sockets.remove(conn)

def deadlock_detector():
    while True:
        time.sleep(1)
        if algorithm_mode != "resolution": continue
        
        wait_for = {}
        for cid, c in cars.items():
            wf = c.get("waiting_for")
            if wf and wf.startswith("F"):
                fork_id = int(wf[1:])
                owner = zone_owners.get(fork_id)
                if owner:
                    wait_for[cid] = owner
                    
        visited = set()
        for start_node in list(wait_for.keys()):
            if start_node in visited: continue
            
            path = []
            curr = start_node
            cycle_found = False
            while curr in wait_for:
                path.append(curr)
                curr = wait_for[curr]
                if curr in path:
                    cycle_start = path.index(curr)
                    cycle = path[cycle_start:]
                    victim = cycle[-1]
                    if victim in cars:
                        cars[victim]["preempt"] = True
                    cycle_found = True
                    break
            if cycle_found: break
            for p in path: visited.add(p)

def start_server():
    HOST = '127.0.0.1'
    PORT = 65432
    threading.Thread(target=broadcast_state, daemon=True).start()
    threading.Thread(target=deadlock_detector, daemon=True).start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Dining Philosophers Server running on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()
