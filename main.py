import pygame
import sqlite3
import random
import sys
import os
import gspread
import math
import datetime
from google.oauth2.service_account import Credentials
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Initialize Pygame Core Modules
pygame.init()
pygame.font.init()
pygame.mixer.init()

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 30
GRID_SIZE = 60  

# Premium Asset Palette
CLR_BG = (34, 34, 38)            
CLR_GRID = (46, 46, 52)          
CLR_PANEL = (24, 24, 28)         
CLR_PANEL_LIGHT = (40, 40, 46)   
CLR_TEXT = (230, 230, 235)       
CLR_MUTED = (140, 140, 150)      
CLR_PRIMARY = (99, 102, 241)     
CLR_SUCCESS = (16, 185, 129)     
CLR_ERROR = (239, 68, 68)        
CLR_WHITE = (255, 255, 255)
CLR_ROAD = (20, 20, 22)          
CLR_MARKING = (200, 200, 205)    
CLR_ACCENT_YELLOW = (245, 158, 11)

FONT_SM = pygame.font.SysFont("Segoe UI", 13)
FONT_MD = pygame.font.SysFont("Segoe UI", 16, bold=True)
FONT_LG = pygame.font.SysFont("Segoe UI", 24, bold=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "velocity.db")

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS profiles (username TEXT PRIMARY KEY, password TEXT)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS layouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            tile_x INTEGER, 
            tile_y INTEGER, 
            asset_type TEXT,
            orientation TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dynamic_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            retained_funds INTEGER,
            cleared_units INTEGER,
            congestion_percentage INTEGER
        )
    """)
    try:
        cursor.execute("INSERT INTO profiles VALUES ('riley', '123')")
    except sqlite3.IntegrityError:
        pass
    conn.commit()
    conn.close()

init_database()

def trigger_system_beep():
    try:
        sample_rate = 22050
        duration = 0.15
        num_samples = int(sample_rate * duration)
        buffer = bytearray()
        for i in range(num_samples):
            val = 110 if (i // 18) % 2 == 0 else -110
            buffer.append(val & 255)
        sound = pygame.mixer.Sound(buffer=buffer)
        sound.set_volume(0.1)
        sound.play()
    except Exception:
        pass

def draw_rounded_rect_alpha(surface, color, rect, radius, alpha=255):
    shape_surf = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(shape_surf, (*color, alpha), (0, 0, rect[2], rect[3]), border_radius=radius)
    surface.blit(shape_surf, (rect[0], rect[1]))

class CityEnvironment:
    def __init__(self):
        self.zones = {}
        random.seed(101) 
        for bx in range(1, 45, 5):
            for by in range(0, 22, 4):
                if random.random() < 0.65:
                    zone_type = random.choice(["Skyscraper", "Residential", "Commercial Park"])
                    for dx in range(2):
                        for dy in range(2):
                            self.zones[(bx + dx, by + dy)] = zone_type

    def draw_zone_tile(self, surface, zone_type, px, py):
        if zone_type == "Skyscraper":
            draw_rounded_rect_alpha(surface, (45, 55, 72), (px+2, py+2, GRID_SIZE-4, GRID_SIZE-4), 6, 180)
            pygame.draw.rect(surface, (71, 85, 105), (px+6, py+6, GRID_SIZE-12, GRID_SIZE-12), border_radius=4)
            for wx in range(px+12, px+GRID_SIZE-12, 10):
                pygame.draw.line(surface, (147, 197, 253, 200), (wx, py+12), (wx, py+GRID_SIZE-12), 2)
        elif zone_type == "Commercial Park":
            draw_rounded_rect_alpha(surface, (30, 41, 59), (px+2, py+2, GRID_SIZE-4, GRID_SIZE-4), 4, 150)
            pygame.draw.circle(surface, (14, 116, 144), (px+30, py+30), 14, 2)
            pygame.draw.circle(surface, CLR_PRIMARY, (px+30, py+30), 6)
        elif zone_type == "Residential":
            draw_rounded_rect_alpha(surface, (51, 65, 85), (px+2, py+2, GRID_SIZE-4, GRID_SIZE-4), 4, 160)
            pygame.draw.polygon(surface, (148, 163, 184), [(px+10, py+44), (px+30, py+16), (px+50, py+44)])

class VectorSpriteFactory:
    @staticmethod
    def draw_road(surface, asset_type, orientation):
        road_canvas = pygame.Surface((GRID_SIZE, GRID_SIZE))
        road_canvas.fill(CLR_ROAD)
        
        pygame.draw.line(road_canvas, (63, 63, 70), (0, 0), (GRID_SIZE, 0), 2)
        pygame.draw.line(road_canvas, (63, 63, 70), (0, GRID_SIZE-1), (GRID_SIZE, GRID_SIZE-1), 2)

        if asset_type in ["Standard Lane", "Adaptive Light"]:
            pygame.draw.line(road_canvas, CLR_ACCENT_YELLOW, (0, 28), (GRID_SIZE, 28), 1)
            pygame.draw.line(road_canvas, CLR_ACCENT_YELLOW, (0, 31), (GRID_SIZE, 31), 1)
            for x in range(0, GRID_SIZE, 20):
                pygame.draw.line(road_canvas, CLR_MARKING, (x, 14), (x+10, 14), 1)
                pygame.draw.line(road_canvas, CLR_MARKING, (x, 46), (x+10, 46), 1)
                    
        elif asset_type == "Turning Lane":
            pygame.draw.line(road_canvas, CLR_ACCENT_YELLOW, (0, 30), (GRID_SIZE, 30), 2)
            pygame.draw.line(road_canvas, CLR_WHITE, (18, 44), (36, 44), 2)
            pygame.draw.polygon(road_canvas, CLR_WHITE, [(18, 40), (10, 44), (18, 48)])

        elif asset_type == "Merge Lane":
            pygame.draw.line(road_canvas, CLR_MARKING, (0, 14), (GRID_SIZE, 0), 2)
            for x in range(0, GRID_SIZE, 15):
                pygame.draw.line(road_canvas, CLR_WHITE, (x, 44), (x+6, 44), 1)

        if orientation == "0": rot_angle = 0
        elif orientation == "90": rot_angle = 90
        elif orientation == "180": rot_angle = 180
        elif orientation == "270": rot_angle = 270
        else: rot_angle = 0
            
        final_rotated_surf = pygame.transform.rotate(road_canvas, rot_angle)
        surface.blit(final_rotated_surf, (0, 0))

    @staticmethod
    def draw_massive_roundabout(surface):
        surface.fill((28, 33, 31))
        cx, cy = 90, 90
        pygame.draw.circle(surface, (63, 63, 70), (cx, cy), 86, 2)
        pygame.draw.circle(surface, CLR_ROAD, (cx, cy), 84)
        pygame.draw.circle(surface, CLR_WHITE, (cx, cy), 62, 1)
        
        pygame.draw.rect(surface, CLR_ROAD, (60, 0, 60, 24))
        pygame.draw.rect(surface, CLR_ROAD, (60, 156, 60, 24))
        pygame.draw.rect(surface, CLR_ROAD, (0, 60, 24, 60))
        pygame.draw.rect(surface, CLR_ROAD, (156, 60, 24, 60))

        pygame.draw.circle(surface, (30, 41, 59), (cx, cy), 42)
        pygame.draw.circle(surface, (16, 116, 134), (cx, cy), 38)
        pygame.draw.circle(surface, (13, 148, 136), (cx, cy), 32)

    @staticmethod
    def draw_premium_traffic_light(surface, px, py, state):
        housing_w, housing_h = 14, 36
        hx = px + (GRID_SIZE // 2) - (housing_w // 2)
        hy = py + (GRID_SIZE // 2) - (housing_h // 2)
        
        pygame.draw.rect(surface, (20, 20, 25), (hx, hy, housing_w, housing_h), border_radius=4)
        pygame.draw.rect(surface, (50, 50, 60), (hx, hy, housing_w, housing_h), 1, border_radius=4)
        
        red_color = (255, 50, 50) if state == "RED" else (60, 20, 20)
        yellow_color = (245, 158, 11) if state == "YELLOW" else (70, 50, 10)
        green_color = (16, 185, 129) if state == "GREEN" else (10, 50, 30)
        
        pygame.draw.circle(surface, red_color, (hx + 7, hy + 7), 4)
        pygame.draw.circle(surface, yellow_color, (hx + 7, hy + 18), 4)
        pygame.draw.circle(surface, green_color, (hx + 7, hy + 29), 4)

    @staticmethod
    def draw_vector_car(surface, x, y, color, rotation_angle=0, brake_lights_on=False, car_type="Sedan"):
        if car_type == "Municipal Bus": w, h = 48, 20; radius = 3
        elif car_type == "Pickup Truck": w, h = 38, 19; radius = 4
        elif car_type == "Compact Car": w, h = 26, 15; radius = 6
        else: w, h = 34, 17; radius = 5
            
        shadow_offset = 4
        shadow_surf = pygame.Surface((w + 8, h + 8), pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, (0, 0, 0, 90), (4, 4, w, h), border_radius=radius)
        rotated_shadow = pygame.transform.rotate(shadow_surf, math.degrees(-rotation_angle))
        surface.blit(rotated_shadow, rotated_shadow.get_rect(center=(x + shadow_offset, y + shadow_offset)).topleft)

        beam_surf = pygame.Surface((120, 80), pygame.SRCALPHA)
        pygame.draw.polygon(beam_surf, (253, 224, 71, 45), [(40, 40), (110, 15), (110, 65)])
        pygame.draw.polygon(beam_surf, (253, 224, 71, 15), [(40, 40), (120, 5), (120, 75)])
        rotated_beam = pygame.transform.rotate(beam_surf, math.degrees(-rotation_angle))
        beam_offset_x = math.cos(rotation_angle) * 20
        beam_offset_y = math.sin(rotation_angle) * 20
        surface.blit(rotated_beam, rotated_beam.get_rect(center=(x + beam_offset_x, y + beam_offset_y)).topleft)

        car_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(car_surf, color, (0, 0, w, h), border_radius=radius)
        pygame.draw.rect(car_surf, (255, 255, 255, 60), (0, 0, w, h), 1, border_radius=radius)

        if car_type == "Municipal Bus":
            pygame.draw.rect(car_surf, (15, 23, 42), (8, 2, w-14, h-4), border_radius=1)
        else: 
            pygame.draw.rect(car_surf, (15, 23, 42), (w-12, 2, 8, h-4), border_radius=2)
            pygame.draw.rect(car_surf, (30, 41, 59), (8, 3, w-22, h-6))

        if brake_lights_on:
            pygame.draw.rect(car_surf, (255, 50, 50), (0, 1, 2, 4), border_radius=1)
            pygame.draw.rect(car_surf, (255, 50, 50), (0, h-5, 2, 4), border_radius=1)
        else:
            pygame.draw.rect(car_surf, (185, 28, 28), (0, 1, 2, 3), border_radius=1)
            pygame.draw.rect(car_surf, (185, 28, 28), (0, h-4, 2, 3), border_radius=1)

        rotated_car = pygame.transform.rotate(car_surf, math.degrees(-rotation_angle))
        surface.blit(rotated_car, rotated_car.get_rect(center=(x, y)).topleft)

class VeloCityEngine:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Velo-City: Premium Urban Traffic Architect")
        self.clock = pygame.time.Clock()
        self.app_state = "LOGIN"
        
        self.input_user = ""
        self.input_pass = ""
        self.active_field = "USER"
        self.login_error = False
        self.shake_frames = 0
        
        self.camera_x = 0
        self.camera_y = 0
        self.is_dragging = False
        self.drag_start_mouse = (0, 0)
        self.drag_start_camera = (0, 0)
        
        self.budget = 750000
        self.selected_tool = "Standard Lane"
        self.current_orientation = "0" 
        self.grid_matrix = {}
        self.vehicles = []
        self.sim_active = False
        self.spawn_probability = 0.20
        
        self.congestion_index = 0
        self.cars_cleared = 0
        self.traffic_light_timer = 0
        self.traffic_light_state = "GREEN"
        
        self.sheet_error_message = ""
        self.wallet_error_active = False
        self.history_records = []
        self.display_history_modal = False

        self.city_env = CityEnvironment()
        self.costs = {
            "Standard Lane": 500, 
            "Turning Lane": 800, 
            "Merge Lane": 1200, 
            "Roundabout": 50000, 
            "Adaptive Light": 2000
        }

    def run_loop(self):
        while True:
            self.handle_events()
            self.handle_continuous_input()  # Handles continuous hold-and-drag mechanics
            self.screen.fill(CLR_BG)
            
            if self.app_state == "LOGIN":
                self.render_login_screen()
            elif self.app_state == "DASHBOARD":
                self.render_dashboard()
            elif self.app_state == "BUILD_MODE":
                self.render_build_mode()
                
            pygame.display.flip()
            self.clock.tick(FPS)

    def handle_continuous_input(self):
        """Processes continuous hold down inputs every frame (e.g., drag bulldozing)"""
        if self.app_state == "BUILD_MODE" and not (self.wallet_error_active or self.sheet_error_message or self.display_history_modal):
            mouse_buttons = pygame.mouse.get_pressed()
            mx, my = pygame.mouse.get_pos()
            
            # Continuous dragging deletion loop if bulldozer is active and left click is held down
            if mouse_buttons[0] and mx < 1000 and self.selected_tool == "BULLDOZER":
                world_x = mx - self.camera_x
                world_y = my - self.camera_y
                tx = world_x // GRID_SIZE
                ty = world_y // GRID_SIZE
                self.process_grid_deletion(tx, ty)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
                
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE and self.app_state != "LOGIN":
                    self.sim_active = False
                    self.display_history_modal = False
                    self.wallet_error_active = False
                    self.sheet_error_message = ""
                    self.app_state = "DASHBOARD"
                if event.key == pygame.K_r:
                    current_deg = int(self.current_orientation)
                    next_deg = (current_deg + 90) % 360
                    self.current_orientation = str(next_deg)
                    
                if self.app_state == "LOGIN":
                    if event.key == pygame.K_TAB:
                        self.active_field = "PASS" if self.active_field == "USER" else "USER"
                    elif event.key == pygame.K_RETURN:
                        self.process_login_attempt()
                    elif event.key == pygame.K_BACKSPACE:
                        if self.active_field == "USER": self.input_user = self.input_user[:-1]
                        else: self.input_pass = self.input_pass[:-1]
                    else:
                        if event.unicode.isprintable():
                            if self.active_field == "USER": self.input_user += event.unicode
                            else: self.input_pass += event.unicode

            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                
                if self.app_state == "LOGIN":
                    offset_x = int(math.sin(self.shake_frames * 1.5) * 6) if self.shake_frames > 0 else 0
                    if (140 + offset_x) <= mx <= (140 + offset_x + 360) and 230 <= my <= 272: self.active_field = "USER"
                    elif (140 + offset_x) <= mx <= (140 + offset_x + 360) and 330 <= my <= 372: self.active_field = "PASS"
                    elif (140 + offset_x) <= mx <= (140 + offset_x + 360) and 420 <= my <= 466: self.process_login_attempt()
                        
                elif self.app_state == "DASHBOARD":
                    if 490 <= mx <= 790 and 250 <= my <= 300:
                        if self.import_google_sheets_data(): self.app_state = "BUILD_MODE"
                    elif 490 <= mx <= 790 and 330 <= my <= 380:
                        self.load_grid_from_database()
                        self.app_state = "BUILD_MODE"
                    elif 490 <= mx <= 790 and 410 <= my <= 460:
                        self.input_user = ""; self.input_pass = ""; self.app_state = "LOGIN"
                        
                elif self.app_state == "BUILD_MODE":
                    if self.wallet_error_active or self.sheet_error_message or self.display_history_modal:
                        self.wallet_error_active = False; self.sheet_error_message = ""; self.display_history_modal = False
                        return

                    if mx > 1000: 
                        if 115 <= my <= 145: self.selected_tool = "Standard Lane"
                        elif 155 <= my <= 185: self.selected_tool = "Turning Lane"
                        elif 195 <= my <= 225: self.selected_tool = "Merge Lane"
                        elif 235 <= my <= 265: self.selected_tool = "Roundabout"
                        elif 275 <= my <= 305: self.selected_tool = "Adaptive Light"
                        elif 315 <= my <= 345: self.selected_tool = "BULLDOZER"  
                        elif 352 <= my <= 377: self.clear_entire_plot() # Clear Plot Button Trigger
                        elif 395 <= my <= 420: self.fetch_history_logs()
                        elif 435 <= my <= 470:
                            self.sim_active = not self.sim_active
                            if self.sim_active: self.vehicles.clear()
                            else: self.commit_session_metrics()
                        elif 485 <= my <= 520: self.trigger_pdf_export_routine()
                        elif 535 <= my <= 565: self.sim_active = False; self.app_state = "DASHBOARD"
                        elif 585 <= my <= 615: self.sim_active = False; self.input_user = ""; self.input_pass = ""; self.app_state = "LOGIN"
                    else:
                        world_x = mx - self.camera_x
                        world_y = my - self.camera_y
                        tx = world_x // GRID_SIZE
                        ty = world_y // GRID_SIZE
                        
                        if event.button == 1: 
                            if self.selected_tool != "BULLDOZER": # Handled continuously now
                                self.process_grid_placement(tx, ty)
                        elif event.button in [2, 3]: 
                            self.is_dragging = True
                            self.drag_start_mouse = (mx, my)
                            self.drag_start_camera = (self.camera_x, self.camera_y)

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button in [2, 3]: self.is_dragging = False

            if event.type == pygame.MOUSEMOTION:
                if self.app_state == "BUILD_MODE" and self.is_dragging:
                    mx, my = pygame.mouse.get_pos()
                    self.camera_x = self.drag_start_camera[0] + (mx - self.drag_start_mouse[0])
                    self.camera_y = self.drag_start_camera[1] + (my - self.drag_start_mouse[1])

    def process_login_attempt(self):
        if self.input_user == "riley" and self.input_pass == "123":
            self.login_error = False; self.app_state = "DASHBOARD"
        else:
            self.login_error = True; self.shake_frames = 15

    def render_login_screen(self):
        self.screen.fill((20, 20, 25))
        offset_x = int(math.sin(self.shake_frames * 1.5) * 6) if self.shake_frames > 0 else 0
        if self.shake_frames > 0: self.shake_frames -= 1
        
        draw_rounded_rect_alpha(self.screen, CLR_PANEL, (100 + offset_x, 80, 440, 560), 12, 255)
        pygame.draw.rect(self.screen, (40, 40, 50), (100 + offset_x, 80, 440, 560), 1, border_radius=12)
        
        self.screen.blit(FONT_LG.render("VELO-CITY WORKSPACE", True, CLR_TEXT), (130 + offset_x, 120))
        pygame.draw.line(self.screen, CLR_GRID, (130 + offset_x, 160), (500 + offset_x, 160), 1)
        
        self.screen.blit(FONT_MD.render("Enter Engine Username", True, CLR_MUTED), (140 + offset_x, 200))
        pygame.draw.rect(self.screen, (30, 30, 36), (140 + offset_x, 230, 360, 42), border_radius=6)
        active_border_color = CLR_PRIMARY if self.active_field == "USER" else (50, 50, 60)
        pygame.draw.rect(self.screen, active_border_color, (140 + offset_x, 230, 360, 42), 1, border_radius=6)
        self.screen.blit(FONT_MD.render(self.input_user + ("|" if self.active_field == "USER" else ""), True, CLR_WHITE), (154 + offset_x, 241))
        
        self.screen.blit(FONT_MD.render("Security Passkey", True, CLR_MUTED), (140 + offset_x, 300))
        pygame.draw.rect(self.screen, (30, 30, 36), (140 + offset_x, 330, 360, 42), border_radius=6)
        active_border_color = CLR_PRIMARY if self.active_field == "PASS" else (50, 50, 60)
        pygame.draw.rect(self.screen, active_border_color, (140 + offset_x, 330, 360, 42), 1, border_radius=6)
        self.screen.blit(FONT_MD.render("*" * len(self.input_pass) + ("|" if self.active_field == "PASS" else ""), True, CLR_WHITE), (154 + offset_x, 341))
        
        btn_box = pygame.Rect(140 + offset_x, 420, 360, 46)
        pygame.draw.rect(self.screen, CLR_PRIMARY, btn_box, border_radius=6)
        self.screen.blit(FONT_MD.render("INITIALIZE SYSTEM ENGINE", True, CLR_WHITE), (218 + offset_x, 433))
        
        if self.login_error:
            self.screen.blit(FONT_MD.render("Authentication Key Error", True, CLR_ERROR), (230 + offset_x, 495))

        right_panel = pygame.Rect(580, 80, 600, 560)
        draw_rounded_rect_alpha(self.screen, CLR_PANEL, right_panel, 12, 180)
        pygame.draw.rect(self.screen, (50, 50, 65), right_panel, 1, border_radius=12)
        
        pygame.draw.circle(self.screen, CLR_PRIMARY, (675, 165), 24)
        pygame.draw.circle(self.screen, CLR_WHITE, (675, 160), 8)
        pygame.draw.arc(self.screen, CLR_WHITE, (663, 170, 24, 20), 0, math.pi, 2)
        
        self.screen.blit(FONT_MD.render("MUNICIPAL CLIENT PROFILE:", True, CLR_PRIMARY), (740, 130))
        self.screen.blit(FONT_LG.render("Alex, Junior Civil Engineer", True, CLR_WHITE), (740, 155))
        
        meta_lines = [
            ("PROJECT TARGET", "Aurora Central Optimization Workspace Corridor"),
            ("ALLOCATED BUDGET", "$750,000 ESCROW FUNDS"),
            ("CONSULTATION GOAL", "Reduce Peak Hour Bottlenecks & Stabilize Multi-Agent Kinematics")
        ]
        for index, (label, val) in enumerate(meta_lines):
            offset_y = 280 + (index * 75)
            self.screen.blit(FONT_SM.render(label, True, CLR_MUTED), (630, offset_y))
            self.screen.blit(FONT_MD.render(val, True, CLR_TEXT), (630, offset_y + 20))

    def render_dashboard(self):
        self.screen.fill((20, 20, 25))
        draw_rounded_rect_alpha(self.screen, CLR_PANEL, (340, 100, 600, 480), 12, 255)
        pygame.draw.rect(self.screen, (50, 50, 60), (340, 100, 600, 480), 1, border_radius=12)
        self.screen.blit(FONT_LG.render("VELO-CITY CENTRAL CONTROLLER", True, CLR_WHITE), (455, 140))
        
        opts = [
            ("IMPORT SHEET DATA & RUN WORKSPACE", 240, CLR_PRIMARY),
            ("RESTORE LOCAL AUTO-SAVED CORRIDOR", 320, CLR_PANEL_LIGHT),
            ("LOG OUT CURRENT PROFILE SESSION", 400, (50, 50, 55))
        ]
        for label, y, bg_c in opts:
            pygame.draw.rect(self.screen, bg_c, (440, y, 400, 52), border_radius=6)
            self.screen.blit(FONT_MD.render(label, True, CLR_WHITE), (440 + (200 - FONT_MD.size(label)[0]//2), y + 16))
        
        if self.sheet_error_message:
            self.screen.blit(FONT_MD.render(self.sheet_error_message, True, CLR_ERROR), (545, 485))

    def import_google_sheets_data(self):
        cred_path = os.path.join(BASE_DIR, "credentials.json")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        try:
            creds = Credentials.from_service_account_file(cred_path, scopes=scopes)
            client = gspread.authorize(creds)
            sheet = client.open("Velo-City_Traffic_Data").sheet1
            
            cell_raw = sheet.acell("B2").value
            cars_per_hour = int(cell_raw) 
            self.spawn_probability = max(0.05, min(0.40, cars_per_hour / 3600.0))
            self.sheet_error_message = ""
            return True
        except (ValueError, TypeError, Exception):
            self.sheet_error_message = "Error: Invalid File Format"
            trigger_system_beep()
            return False

    def trigger_pdf_export_routine(self):
        budget_spent = 750000 - self.budget
        pdf_path = os.path.join(BASE_DIR, "Velo_City_Report.pdf")
        try:
            doc = SimpleDocTemplate(pdf_path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
            story = []
            styles = getSampleStyleSheet()
            
            title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=22, textColor=colors.HexColor('#1E1E24'), spaceAfter=15)
            th_style = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=11, textColor=colors.white)
            td_style = ParagraphStyle('TD', fontName='Helvetica', fontSize=11, textColor=colors.HexColor('#2E2E35'))
            
            story.append(Paragraph("Velo-City Infrastructure Optimization Analytics", title_style))
            story.append(Paragraph(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", td_style))
            story.append(Spacer(1, 20))
            
            data_table = [
                [Paragraph("Metric Field Descriptor", th_style), Paragraph("Logged Value", th_style)],
                [Paragraph("Initial Capital Reserves", td_style), Paragraph("$750,000", td_style)],
                [Paragraph("Retained Funds Balance", td_style), Paragraph(f"${self.budget:,}", td_style)],
                [Paragraph("Calculated Expenditures", td_style), Paragraph(f"${budget_spent:,}", td_style)],
                [Paragraph("Total System Cleared Units", td_style), Paragraph(str(self.cars_cleared), td_style)],
                [Paragraph("Corridor Peak Congestion Rating", td_style), Paragraph(f"{int(self.congestion_index)}%", td_style)]
            ]
            
            t = Table(data_table, colWidths=[280, 240])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (1,0), colors.HexColor('#6366F1')),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 10),
                ('TOPPADDING', (0,0), (-1,-1), 10),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
                ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F8FAFC'))
            ]))
            story.append(t)
            doc.build(story)
        except Exception as e:
            print(f"PDF Infrastructure Generator Exception: {e}")

    def process_grid_placement(self, tx, ty):
        needed = self.costs[self.selected_tool]
        if (tx, ty) in self.city_env.zones or tx < 0 or ty < 0: return

        if self.budget < needed:
            self.wallet_error_active = True
            trigger_system_beep()
            return

        if self.selected_tool == "Roundabout":
            for dx in range(3):
                for dy in range(3):
                    if (tx + dx, ty + dy) in self.grid_matrix or (tx + dx, ty + dy) in self.city_env.zones: return 
            
            self.budget -= needed
            self.grid_matrix[(tx, ty)] = {"type": "Roundabout", "rotation": "0", "master": (tx, ty)}
            for dx in range(3):
                for dy in range(3):
                    if not (dx == 0 and dy == 0):
                        self.grid_matrix[(tx + dx, ty + dy)] = {"type": "Roundabout_Sub", "master": (tx, ty)}
            self.save_layout_to_db(tx, ty, "Roundabout", "0")
        else:
            if (tx, ty) in self.grid_matrix: return
            self.budget -= needed
            self.grid_matrix[(tx, ty)] = {"type": self.selected_tool, "rotation": self.current_orientation}
            self.save_layout_to_db(tx, ty, self.selected_tool, self.current_orientation)

    def save_layout_to_db(self, tx, ty, asset, orientation):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO layouts (tile_x, tile_y, asset_type, orientation) VALUES (?, ?, ?, ?)", (tx, ty, asset, orientation))
            conn.commit(); conn.close()
        except Exception as e: print(f"Database Auto-Save Error: {e}")

    def process_grid_deletion(self, tx, ty):
        if (tx, ty) not in self.grid_matrix: return
        node = self.grid_matrix[(tx, ty)]
        
        if node["type"] in ["Roundabout", "Roundabout_Sub"]:
            mx, my = node["master"]
            self.budget += self.costs["Roundabout"]
            for dx in range(3):
                for dy in range(3):
                    if (mx + dx, my + dy) in self.grid_matrix:
                        del self.grid_matrix[(mx + dx, my + dy)]
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM layouts WHERE tile_x = ? AND tile_y = ?", (mx, my))
                conn.commit(); conn.close()
            except Exception: pass
        else:
            refund_amount = self.costs[node["type"]]
            self.budget += refund_amount
            del self.grid_matrix[(tx, ty)]
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM layouts WHERE tile_x = ? AND tile_y = ?", (tx, ty))
                conn.commit(); conn.close()
            except Exception: pass

    def clear_entire_plot(self):
        """Wipes all placed layouts instantly from matrix and local tracking storage"""
        self.grid_matrix.clear()
        self.vehicles.clear()
        self.budget = 750000  # Full Escrow Restoration
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM layouts")
            conn.commit(); conn.close()
            trigger_system_beep()
        except Exception as e:
            print(f"Failed to clear database logs: {e}")

    def load_grid_from_database(self):
        self.grid_matrix.clear()
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT tile_x, tile_y, asset_type, orientation FROM layouts")
            for row in c.fetchall():
                tx, ty, asset, orient = row[0], row[1], row[2], row[3]
                if asset == "Roundabout":
                    self.grid_matrix[(tx, ty)] = {"type": "Roundabout", "rotation": "0", "master": (tx, ty)}
                    for dx in range(3):
                        for dy in range(3):
                            if not (dx == 0 and dy == 0):
                                self.grid_matrix[(tx + dx, ty + dy)] = {"type": "Roundabout_Sub", "master": (tx, ty)}
                else:
                    self.grid_matrix[(tx, ty)] = {"type": asset, "rotation": orient}
            conn.close()
        except Exception as e: print(f"Database Load Error: {e}")

    def fetch_history_logs(self):
        self.history_records.clear()
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT timestamp, retained_funds, cleared_units, congestion_percentage FROM dynamic_history ORDER BY id DESC LIMIT 5")
            self.history_records = c.fetchall()
            conn.close()
            self.display_history_modal = True
        except Exception: pass

    def commit_session_metrics(self):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO dynamic_history (timestamp, retained_funds, cleared_units, congestion_percentage) VALUES (?, ?, ?, ?)", (now_str, self.budget, self.cars_cleared, int(self.congestion_index)))
            conn.commit(); conn.close()
        except Exception: pass

    def get_next_path_target(self, tx, ty, entry_face):
        node = self.grid_matrix.get((tx, ty))
        if not node: return None
        asset_type = node["type"]
        orient = node.get("rotation", "0")
        
        if asset_type in ["Roundabout", "Roundabout_Sub"]:
            mx, my = node["master"]
            if entry_face == "LEFT" and ty == my + 1: return (mx, my, "ROUNDABOUT_ORBIT", True)
            if entry_face == "TOP" and tx == mx + 1: return (mx, my, "ROUNDABOUT_ORBIT", True)
            if entry_face == "BOTTOM" and tx == mx + 1: return (mx, my, "ROUNDABOUT_ORBIT", True)
            if entry_face == "RIGHT" and ty == my + 1: return (mx, my, "ROUNDABOUT_ORBIT", True)

        if orient in ["0", "180"]:
            if entry_face == "LEFT": return (tx + 1, ty, "LEFT", False)
            if entry_face == "RIGHT": return (tx - 1, ty, "RIGHT", False)
        else:
            if entry_face == "TOP": return (tx, ty + 1, "TOP", False)
            if entry_face == "BOTTOM": return (tx, ty - 1, "BOTTOM", False)
        return (tx + 1, ty, "LEFT", False) if entry_face == "LEFT" else None

    def render_build_mode(self):
        start_tx = max(0, -self.camera_x // GRID_SIZE)
        end_tx = start_tx + (1000 // GRID_SIZE) + 2
        start_ty = max(0, -self.camera_y // GRID_SIZE)
        end_ty = start_ty + (720 // GRID_SIZE) + 2

        for tx in range(start_tx, end_tx):
            for ty in range(start_ty, end_ty):
                px = self.camera_x + (tx * GRID_SIZE)
                py = self.camera_y + (ty * GRID_SIZE)
                if px < 1000: pygame.draw.rect(self.screen, CLR_GRID, (px, py, GRID_SIZE, GRID_SIZE), 1)

        for pos, zone in self.city_env.zones.items():
            px = self.camera_x + (pos[0] * GRID_SIZE)
            py = self.camera_y + (pos[1] * GRID_SIZE)
            if px < 1000: self.city_env.draw_zone_tile(self.screen, zone, px, py)
                
        for pos, asset in self.grid_matrix.items():
            px = self.camera_x + (pos[0] * GRID_SIZE)
            py = self.camera_y + (pos[1] * GRID_SIZE)
            
            if px < 1000: 
                if asset["type"] == "Roundabout":
                    huge_surface = pygame.Surface((GRID_SIZE*3, GRID_SIZE*3), pygame.SRCALPHA)
                    VectorSpriteFactory.draw_massive_roundabout(huge_surface)
                    self.screen.blit(huge_surface, (px, py))
                elif asset["type"] != "Roundabout_Sub":
                    road_surface = pygame.Surface((GRID_SIZE, GRID_SIZE))
                    VectorSpriteFactory.draw_road(road_surface, asset["type"], asset["rotation"])
                    self.screen.blit(road_surface, (px, py))
                
                if asset["type"] == "Adaptive Light":
                    VectorSpriteFactory.draw_premium_traffic_light(self.screen, px, py, self.traffic_light_state)

        if self.sim_active:
            self.traffic_light_timer += 1
            lane_1_count = sum(1 for c in self.vehicles if c["mode"] == "STANDARD_PATH" and c["ty"] == 4 and c["tx"] < 12)
            if lane_1_count >= 12:
                self.traffic_light_state = "GREEN"; self.traffic_light_timer = 0
            else:
                if self.traffic_light_timer % 100 == 0:
                    self.traffic_light_state = "RED" if self.traffic_light_state == "GREEN" else "GREEN"
            
            valid_spawns = [pos[1] for pos, asset in self.grid_matrix.items() if pos[0] == 0 and asset.get("rotation") in ["0", "180"]]
            
            if valid_spawns and random.random() < self.spawn_probability and len(self.vehicles) < 105:
                chosen_ty = random.choice(valid_spawns)
                car_colors = [(99, 102, 241), (239, 68, 68), (16, 185, 129), (245, 158, 11), (168, 85, 247)]
                c_type = random.choice(["Sedan", "Pickup Truck", "Compact Car", "Municipal Bus"])
                self.vehicles.append({
                    "id": random.randint(100, 999), "mode": "STANDARD_PATH", "tx": 0, "ty": chosen_ty, "entry_face": "LEFT", "progress": 0.0, 
                    "speed": 3.8, "color": random.choice(car_colors), "world_x": 0.0, "world_y": 0.0, "angle": 0.0,
                    "rb_master": None, "rb_angle": math.pi, "rb_exit_face": "RIGHT", "brakes_applied": False, "type": c_type
                })
                
            stopped_cars_time = 0; total_active_cars = 0
            
            for i, car in enumerate(self.vehicles):
                if car["tx"] > 40: continue
                total_active_cars += 1
                
                if car["mode"] == "STANDARD_PATH":
                    node = self.grid_matrix.get((car["tx"], car["ty"]))
                    base_target_speed = 3.6 if car["type"] == "Municipal Bus" else 4.5
                    car["brakes_applied"] = False
                    
                    is_following_close = False
                    for j, other_car in enumerate(self.vehicles):
                        if i != j and other_car["mode"] == "STANDARD_PATH" and other_car["ty"] == car["ty"]:
                            dist = (other_car["tx"] * GRID_SIZE + other_car["progress"] * GRID_SIZE) - (car["tx"] * GRID_SIZE + car["progress"] * GRID_SIZE)
                            if 0 < dist < 46: is_following_close = True; break
                    
                    if node and node["type"] == "Adaptive Light" and self.traffic_light_state == "RED" and car["progress"] > 0.55:
                        car["speed"] = max(0.0, car["speed"] - 0.7); car["brakes_applied"] = True
                    elif is_following_close:
                        car["speed"] = max(0.0, car["speed"] - 0.9); car["brakes_applied"] = True
                    else:
                        car["speed"] = min(base_target_speed, car["speed"] + 0.4)
                        
                    car["progress"] += (car["speed"] / GRID_SIZE)
                    tile_px = car["tx"] * GRID_SIZE; tile_py = car["ty"] * GRID_SIZE
                    
                    if car["entry_face"] == "LEFT": car["world_x"] = tile_px + (car["progress"] * GRID_SIZE); car["world_y"] = tile_py + 30; car["angle"] = 0.0
                    elif car["entry_face"] == "TOP": car["world_x"] = tile_px + 30; car["world_y"] = tile_py + (car["progress"] * GRID_SIZE); car["angle"] = math.pi / 2
                    elif car["entry_face"] == "BOTTOM": car["world_x"] = tile_px + 30; car["world_y"] = tile_py + ((1.0 - car["progress"]) * GRID_SIZE); car["angle"] = -math.pi / 2
                    
                    if car["speed"] <= 0.1: stopped_cars_time += 1
                    
                    if car["progress"] >= 1.0:
                        next_res = self.get_next_path_target(car["tx"], car["ty"], car["entry_face"])
                        if next_res:
                            ntx, nty, nface, is_curved = next_res
                            if nface == "ROUNDABOUT_ORBIT":
                                car["mode"] = "ROUNDABOUT_ORBIT"; car["rb_master"] = (ntx, nty)
                                car["rb_exit_face"] = random.choice(["TOP", "RIGHT", "BOTTOM"])
                                car["rb_angle"] = math.pi if car["entry_face"] == "LEFT" else 0.0
                            else: car["tx"], car["ty"], car["entry_face"], car["progress"] = ntx, nty, nface, 0.0
                        else: car["tx"] = 9999 

                elif car["mode"] == "ROUNDABOUT_ORBIT":
                    mx, my = car["rb_master"]
                    cx, cy = (mx * GRID_SIZE) + 90, (my * GRID_SIZE) + 90
                    radius = 72
                    
                    car["rb_angle"] += (car["speed"] / radius)
                    car["world_x"] = cx + (radius * math.cos(car["rb_angle"]))
                    car["world_y"] = cy + (radius * math.sin(car["rb_angle"]))
                    car["angle"] = car["rb_angle"] + (math.pi / 2)
                    
                    current_deg = math.degrees(car["rb_angle"]) % 360
                    if car["rb_exit_face"] == "TOP" and 260 <= current_deg <= 280:
                        if (mx + 1, my - 1) in self.grid_matrix:
                            car["mode"] = "STANDARD_PATH"; car["tx"], car["ty"], car["entry_face"], car["progress"] = mx + 1, my - 1, "BOTTOM", 0.0
                    elif car["rb_exit_face"] == "RIGHT" and (current_deg <= 10 or current_deg >= 350):
                        if (mx + 3, my + 1) in self.grid_matrix:
                            car["mode"] = "STANDARD_PATH"; car["tx"], car["ty"], car["entry_face"], car["progress"] = mx + 3, my + 1, "LEFT", 0.0

                render_x = self.camera_x + int(car["world_x"])
                render_y = self.camera_y + int(car["world_y"])
                if render_x < 1000:
                    VectorSpriteFactory.draw_vector_car(self.screen, render_x, render_y, car["color"], car["angle"], car["brakes_applied"], car["type"])
                
            if total_active_cars > 0: self.congestion_index = min(100, int((stopped_cars_time / total_active_cars) * 100 * 2.2))
            else: self.congestion_index = 0
                
            old_len = len(self.vehicles)
            self.vehicles = [v for v in self.vehicles if v["tx"] < 100]
            self.cars_cleared += (old_len - len(self.vehicles))

        # CONTROL SIDEBAR UI DISPLAY PANEL
        pygame.draw.rect(self.screen, CLR_PANEL, (1000, 0, 280, 720))
        pygame.draw.line(self.screen, (45, 45, 52), (1000, 0), (1000, 720), 2)
        
        pygame.draw.rect(self.screen, (20, 20, 24), (1015, 15, 250, 75), border_radius=6)
        pygame.draw.rect(self.screen, (55, 55, 65), (1015, 15, 250, 75), 1, border_radius=6)
        self.screen.blit(FONT_SM.render("ESCROW RESERVES ACCT", True, CLR_MUTED), (1030, 24))
        self.screen.blit(FONT_LG.render(f"${self.budget:,}", True, CLR_WHITE), (1030, 44))
        
        tools = ["Standard Lane", "Turning Lane", "Merge Lane", "Roundabout", "Adaptive Light"]
        for i, tool in enumerate(tools):
            ty = 115 + (i * 38)
            is_sel = (self.selected_tool == tool)
            b_color = CLR_PRIMARY if is_sel else (35, 35, 40)
            t_color = CLR_WHITE if is_sel else CLR_TEXT
            pygame.draw.rect(self.screen, b_color, (1015, ty, 250, 32), border_radius=4)
            if not is_sel: pygame.draw.rect(self.screen, (55, 55, 62), (1015, ty, 250, 32), 1, border_radius=4)
            suffix = f" ({self.current_orientation}°)" if is_sel and tool != "Roundabout" else ""
            self.screen.blit(FONT_SM.render(f"{tool}{suffix} [${self.costs[tool]:,}]", True, t_color), (1028, ty + 7))
            
        b_del = CLR_ERROR if self.selected_tool == "BULLDOZER" else (35, 35, 40)
        t_del = CLR_WHITE if self.selected_tool == "BULLDOZER" else CLR_ERROR
        pygame.draw.rect(self.screen, b_del, (1015, 315, 250, 32), border_radius=4)
        pygame.draw.rect(self.screen, CLR_ERROR, (1015, 315, 250, 32), 1, border_radius=4)
        self.screen.blit(FONT_SM.render("BULLDOZER (HOLD & DRAG)", True, t_del), (1028, 322))
            
        # CLEAR ENTIRE PLOT BUTTON RENDERING
        pygame.draw.rect(self.screen, (40, 20, 20), (1015, 352, 250, 25), border_radius=4)
        pygame.draw.rect(self.screen, CLR_ERROR, (1015, 352, 250, 25), 1, border_radius=4)
        self.screen.blit(FONT_SM.render("WIPE / CLEAR ENTIRE PLOT", True, CLR_ERROR), (1060, 356))

        pygame.draw.rect(self.screen, (45, 45, 52), (1015, 395, 250, 25), border_radius=4)
        pygame.draw.rect(self.screen, (65, 65, 75), (1015, 395, 250, 25), 1, border_radius=4)
        self.screen.blit(FONT_SM.render("VIEW DATABASE HISTORY LOGS", True, CLR_TEXT), (1040, 399))

        sim_color = (225, 110, 40) if self.sim_active else CLR_SUCCESS
        sim_text = "HALT RUNTIME & RE-ARCHITECT" if self.sim_active else "RUN EVALUATION MODEL"
        pygame.draw.rect(self.screen, sim_color, (1015, 435, 250, 36), border_radius=4)
        self.screen.blit(FONT_SM.render(sim_text, True, CLR_WHITE), (1032 if self.sim_active else 1045, 445))
        
        pygame.draw.rect(self.screen, (30, 41, 59), (1015, 485, 250, 36), border_radius=4)
        pygame.draw.rect(self.screen, (51, 65, 85), (1015, 485, 250, 36), 1, border_radius=4)
        self.screen.blit(FONT_SM.render("GENERATE PDF PLOT DATA", True, CLR_WHITE), (1052, 495))
        
        pygame.draw.rect(self.screen, (45, 45, 52), (1015, 535, 250, 30), border_radius=4)
        self.screen.blit(FONT_SM.render("DASHBOARD PORTAL", True, CLR_TEXT), (1072, 542))

        pygame.draw.rect(self.screen, (24, 24, 28), (1015, 580, 250, 28), border_radius=4)
        pygame.draw.rect(self.screen, (50, 50, 55), (1015, 580, 250, 28), 1, border_radius=4)
        self.screen.blit(FONT_SM.render("EXIT CLIENT RUNTIME", True, CLR_MUTED), (1068, 586))
        
        pygame.draw.rect(self.screen, (20, 20, 24), (1015, 624, 250, 84), border_radius=6)
        pygame.draw.rect(self.screen, (45, 45, 52), (1015, 624, 250, 84), 1, border_radius=6)
        self.screen.blit(FONT_SM.render(f"Congestion Threshold: {int(self.congestion_index)}%", True, CLR_TEXT), (1028, 632))
        self.screen.blit(FONT_SM.render(f"Processed Agents: {self.cars_cleared}", True, CLR_TEXT), (1028, 652))
        self.screen.blit(FONT_SM.render(f"Core Engine Latency: {int(self.clock.get_fps())} FPS", True, CLR_MUTED), (1028, 678))

        if self.wallet_error_active:
            veil = pygame.Surface((1280, 720), pygame.SRCALPHA); veil.fill((10, 10, 14, 200)); self.screen.blit(veil, (0, 0))
            modal = pygame.Rect(440, 240, 400, 220)
            pygame.draw.rect(self.screen, CLR_PANEL, modal, border_radius=12)
            pygame.draw.rect(self.screen, CLR_ERROR, modal, 2, border_radius=12)
            self.screen.blit(FONT_LG.render("CAPITAL RESERVES EXHAUSTED", True, CLR_ERROR), (460, 270))
            self.screen.blit(FONT_SM.render("Transaction Halted: Local Infrastructure Account", True, CLR_TEXT), (468, 325))
            self.screen.blit(FONT_SM.render("Budget Table Locked (Criteria 4)", True, CLR_MUTED), (525, 355))
            pygame.draw.rect(self.screen, CLR_ERROR, (540, 395, 200, 36), border_radius=6)
            self.screen.blit(FONT_SM.render("Dismiss Error Code", True, CLR_WHITE), (585, 405))

        if self.display_history_modal:
            veil = pygame.Surface((1280, 720), pygame.SRCALPHA); veil.fill((10, 10, 14, 210)); self.screen.blit(veil, (0, 0))
            modal = pygame.Rect(340, 150, 600, 420)
            pygame.draw.rect(self.screen, CLR_PANEL, modal, border_radius=12)
            pygame.draw.rect(self.screen, CLR_PRIMARY, modal, 2, border_radius=12)
            self.screen.blit(FONT_LG.render("HISTORICAL SIMULATION RUN LOGINDEX", True, CLR_WHITE), (380, 180))
            
            for index, record in enumerate(self.history_records):
                text_line = f"Timestamp: {record[0]}  |  Funds: ${record[1]:,}  |  Units: {record[2]}  |  Jams: {record[3]}%"
                pygame.draw.rect(self.screen, (30, 30, 36), (380, 230 + (index * 48), 520, 38), border_radius=6)
                self.screen.blit(FONT_SM.render(text_line, True, CLR_TEXT), (395, 241 + (index * 48)))
            self.screen.blit(FONT_SM.render("Tap viewport background canvas area to drop active dialog overlay.", True, CLR_MUTED), (380, 520))

if __name__ == "__main__":
    game_engine = VeloCityEngine()
    game_engine.run_loop()