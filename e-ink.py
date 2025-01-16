#!/usr/bin/python
# -*- coding:utf-8 -*-
import time
import psutil
import subprocess
import socket
from datetime import datetime
from waveshare_epd import epd2in13_V4
from PIL import Image, ImageDraw, ImageFont
import os
from collections import deque

class SystemMonitor:
    def __init__(self, history_points=20):  # 20 points for 5 minutes (15-second intervals)
        self.wifi_history = deque(maxlen=history_points)
        self.cpu_history = deque(maxlen=history_points)
        self.temp_history = deque(maxlen=history_points)
        self.current_cpu = 0
        self.current_temp = 0
        
    def update(self):
        self.wifi_history.append(self.get_wifi_signal_strength())
        self.current_cpu = psutil.cpu_percent()
        self.cpu_history.append(self.current_cpu)
        
        try:
            self.current_temp = psutil.sensors_temperatures()['cpu_thermal'][0].current
        except:
            self.current_temp = 0
        self.temp_history.append(self.current_temp)
        
    @staticmethod
    def get_wifi_signal_strength():
        try:
            result = subprocess.run(['iwconfig', 'wlan0'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'Signal level' in line:
                    signal = line.split('Signal level=')[1].split(' ')[0]
                    return int(signal)
            return 0
        except:
            return 0

    def get_wifi_info(self):
        try:
            result = subprocess.run(['iwgetid'], capture_output=True, text=True)
            ssid = result.stdout.split('"')[1] if result.stdout else "Not Connected"
            
            # Get signal strength
            result = subprocess.run(['iwconfig', 'wlan0'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'Signal level' in line:
                    signal = line.split('Signal level=')[1].split(' ')[0]
                    return f"WiFi: {ssid} ({signal}dB)"
            return f"WiFi: {ssid}"
        except:
            return "WiFi: Error"

    @staticmethod
    def get_ip_address():
        try:
            cmd = "hostname -I | cut -d' ' -f1"
            ip = subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
            return f"IP: {ip}"
        except:
            return "IP: Not found"

    @staticmethod
    def get_uptime():
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"Up: {hours}h {minutes}m"

    def get_cpu_usage(self):
        return f"CPU: {self.current_cpu}%"

    def get_memory_usage(self):
        memory = psutil.virtual_memory()
        return f"RAM: {memory.percent}%"

    def get_temperature(self):
        return f"Temp: {self.current_temp:.1f}°C"

class EinkDisplay:
    def __init__(self):
        self.epd = epd2in13_V4.EPD()
        self.epd.init()
        self.width = self.epd.height
        self.height = self.epd.width
        try:
            self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 12)
            self.small_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 10)
        except:
            self.font = ImageFont.load_default()
            self.small_font = ImageFont.load_default()

    def create_status_page(self, monitor):
        image = Image.new('1', (self.width, self.height), 255)
        draw = ImageDraw.Draw(image)

        # Get system information
        current_time = datetime.now()
        datetime_str = f"{current_time.strftime('%I:%M:%S %p')}  {current_time.strftime('%b %d, %Y')}"
        
        status_items = [
            datetime_str,
            socket.gethostname(),
            monitor.get_ip_address(),
            monitor.get_wifi_info(),
            monitor.get_cpu_usage(),
            monitor.get_memory_usage(),
            monitor.get_temperature(),
            monitor.get_uptime()
        ]

        # Draw each line
        y_offset = 2
        for item in status_items:
            draw.text((2, y_offset), item, font=self.font, fill=0)
            y_offset += 14

        # Draw a border
        draw.rectangle((0, 0, self.width-1, self.height-1), outline=0)

        # Rotate and display
        image = image.rotate(180)
        self.epd.display(self.epd.getbuffer(image))

    def create_graph(self, data, title, min_val, max_val, y_label, x_label="Time (5 min)"):
        image = Image.new('1', (self.width, self.height), 255)
        draw = ImageDraw.Draw(image)

        # Graph dimensions
        graph_margin_left = 40
        graph_margin_right = 10
        graph_margin_top = 20
        graph_margin_bottom = 20
        
        y_label_padding = 4 
        graph_start_x = graph_margin_left + y_label_padding
        
        graph_width = self.width - (graph_start_x + graph_margin_right)
        graph_height = self.height - (graph_margin_top + graph_margin_bottom)

        # Draw title
        draw.text((2, 2), title, font=self.font, fill=0)

        # Draw axes
        draw.line((graph_start_x, graph_margin_top, 
                   graph_start_x, self.height-graph_margin_bottom), fill=0)
        draw.line((graph_start_x, self.height-graph_margin_bottom,
                   self.width-graph_margin_right, self.height-graph_margin_bottom), fill=0)

        # Draw Y-axis labels
        num_y_labels = 5
        for i in range(num_y_labels):
            value = max_val - (i * (max_val - min_val) / (num_y_labels - 1))
            y_pos = graph_margin_top + (i * graph_height / (num_y_labels - 1))
            label = f"{int(value)}"
            label_width = draw.textlength(label, font=self.small_font)
            draw.text((graph_start_x - label_width - 2, y_pos - 4), 
                     label, font=self.small_font, fill=0)

        # Draw Y-axis label
        y_label_width = draw.textlength(y_label, font=self.small_font)
        draw.text((8, self.height//2 - y_label_width//2), y_label, 
                 font=self.small_font, fill=0, rotation=90)

        # Draw X-axis label
        x_label_width = draw.textlength(x_label, font=self.small_font)
        draw.text((self.width//2 - x_label_width//2, self.height-15), 
                 x_label, font=self.small_font, fill=0)

        # Plot data points
        if len(data) > 1:
            points = []
            for i, value in enumerate(data):
                x = graph_start_x + (i * (graph_width / (len(data) - 1)))
                y = self.height - (graph_margin_bottom + ((value - min_val) * graph_height / (max_val - min_val)))
                points.append((x, y))

            # Draw lines between points
            for i in range(len(points) - 1):
                draw.line((points[i], points[i+1]), fill=0)

        # Draw border
        draw.rectangle((0, 0, self.width-1, self.height-1), outline=0)

        # Rotate and display
        image = image.rotate(180)
        self.epd.display(self.epd.getbuffer(image))

    def clear(self):
        self.epd.Clear(0xFF)

    def sleep(self):
        self.epd.sleep()

def main():
    display = EinkDisplay()
    monitor = SystemMonitor()
    screen_interval = 10  # Show each screen for 10 seconds
    update_interval = 15  # Update data every 15 seconds
    last_update = 0
    
    try:
        while True:
            current_time = time.time()
            
            # Update system data every 15 seconds
            if current_time - last_update >= update_interval:
                monitor.update()
                last_update = current_time

            # Rotate through screens
            display.create_status_page(monitor)
            time.sleep(screen_interval)
            
            display.create_graph(monitor.wifi_history, 
                               "WiFi Signal Strength", 
                               -100, -20, 
                               "dB")
            time.sleep(screen_interval)
            
            display.create_graph(monitor.cpu_history, 
                               "CPU Usage", 
                               0, 100, 
                               "%")
            time.sleep(screen_interval)
            
            display.create_graph(monitor.temp_history, 
                               "CPU Temperature", 
                               30, 80,
                               "°C")
            time.sleep(screen_interval)
            
    except KeyboardInterrupt:
        print("Cleaning up...")
        display.clear()
        display.sleep()

if __name__ == "__main__":
    main()
