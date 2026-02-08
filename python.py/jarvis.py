import sys
import io
from contextlib import redirect_stderr
from difflib import SequenceMatcher, get_close_matches

# PyAudio hatasını bastır
old_stderr = sys.stderr
sys.stderr = io.StringIO()

import speech_recognition as sr

sys.stderr = old_stderr

import pyttsx3
from datetime import datetime
import json
from pathlib import Path
import os
import re
import subprocess
import webbrowser
from urllib.request import urlopen

# .env dosyasından key'i yükle
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

# OpenAI ChatGPT API
try:
    from openai import OpenAI  # type: ignore
    HAS_OPENAI = True
except:
    HAS_OPENAI = False

try:
    import sounddevice as sd
    from scipy import signal
    HAVE_SOUNDDEVICE = True
except Exception:
    HAVE_SOUNDDEVICE = False

try:
    import win32com.client
    HAS_WIN32COM = True
except:
    HAS_WIN32COM = False

try:
    import numpy as np
except:
    np = None

class JARVIS:
    """
    Iron Man'ın JARVIS'i Benzeri Yapay Zeka Asistanı
    - Ses komutları anlar
    - Görevleri yerine getirir
    - Sesle yanıt verir
    - Kişiselleştirilmiş cevaplar
    """
    
    def __init__(self, name="JARVIS"):
        self.name = name
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 2000  # Daha duyarlı ses algılama
        
        # TTS motoru
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 140)
            self.engine.setProperty('volume', 0.95)
            self.tts_ready = True
        except Exception:
            self.tts_ready = False
        
        # Ses kalitesi
        self.sample_rate = 16000
        self.chunk_size = 2048
        
        # OpenAI ChatGPT Setup
        self.ai_enabled = False
        self.system_prompt = """Adın JARVIS. Iron Man'ın yapay zeka asistanı gibi davranıyorsun. 
Kişisel, yardımcı ve zarif cevaplar Ver. Türkçe ve İngilizce konuş. Cevapların kısa ve öz olsun (2-3 cümle max)."""
        
        if HAS_OPENAI:
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                try:
                    self.ai_client = OpenAI(api_key=api_key)
                    self.ai_enabled = True
                except:
                    self.ai_enabled = False
        
        # Komutlar ve fonksiyonlar
        self.commands = {
            r'.*saat.*|.*zaman.*': self.get_time,
            r'.*hava.*|.*weather.*': self.get_weather,
            r'.*takvim.*|.*tarih.*': self.get_date,
            r'.*dosya.*aç.*|.*open.*': self.open_file,
            r'.*web.*accor.*|.*browser.*|.*site.*': self.open_web,
            r'.*sistem.*|.*bilgisayar.*': self.system_info,
            r'.*kim+|.*who.*|.*ben.*|.*yourself.*': self.introduce,
            r'.*merhaba.*|.*hello.*|.*selam.*': self.greet,
            r'.*çık.*|.*exit.*|.*quit.*': self.goodbye,
        }
        
        self.startup_message()
    
    def speak(self, text):
        """Metni sesle oku"""
        if not self.tts_ready:
            print(f"[SPEAK] {text}")
            return
        
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            print(f"[SPEAK] {text}")
    
    def listen(self):
        """Sesi dinle ve metne çevir"""
        print("[MIC] Dinleniyor... (Sesini konus)\n")
        
        # SoundDevice ile kayıt
        if HAVE_SOUNDDEVICE:
            return self.listen_with_sounddevice()
        
        # Fallback: PyAudio
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=8)
                
            return self.process_audio(audio)
        
        except Exception as e:
            print(f"[WARN] Mikrofon hatası: {e}")
            return None
    
    def listen_with_sounddevice(self):
        """SoundDevice ile ses kaydı"""
        try:
            import struct
            
            duration = 8
            fs = self.sample_rate
            
            # Ses kaydı yap
            recording = sd.rec(
                int(duration * fs), 
                samplerate=fs, 
                channels=1, 
                dtype='int16',
                blocksize=2048
            )
            
            print("[MIC] Kayit basladi... Konusun")
            sd.wait()
            print("[OK] Kayit tamamlandi\n")
            
            # Ses verisini işle
            audio_bytes = recording.tobytes()
            audio = sr.AudioData(audio_bytes, fs, 2)
            
            return self.process_audio(audio)
        
        except Exception as e:
            print(f"[ERROR] SoundDevice hatası: {e}")
            self.speak("Ses kaydı başarısız oldu")
            return None
    
    def process_audio(self, audio):
        """Kaydedilen sesi işle ve tanı"""
        try:
            print("[PROCESS] Metin taniiliyor...")
            # Turkce icin optimize edilmis ayarlar
            text = self.recognizer.recognize_google(audio, language="tr-TR")
            print(f"[OK] Tanilan: {text}\n")
            return text
        
        except sr.UnknownValueError:
            print("[ERROR] Metin anlasilmadi\n")
            self.speak("Ozur dilerim, anlasılmadi. Lutfen tekrar soyleyin")
            return None
        
        except sr.RequestError as e:
            print(f"[ERROR] Google API hatası: {e}\n")
            self.speak("Internete baglanamadi")
            return None
        
        except Exception as e:
            print(f"[ERROR] Tanima hatası: {e}\n")
            return None
    
    def process_command(self, text):
        """Komutları işle ve yanıt ver"""
        if not text:
            return False
        
        text_lower = text.lower().strip()
        print(f"[USER] Sen: {text}\n")
        
        # Komut eşleştir - klasik regex
        for pattern, func in self.commands.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                return func(text)
        
        # Fuzzy matching - benzer kelimeleri bul
        command_keywords = {
            'saat': ['saat', 'zaman', 'time', 'what time', 'saati'],
            'chrome': ['chrome', 'chromite', 'google chrome', 'browser'],
            'dosya': ['dosya', 'file', 'aç', 'open'],
            'web': ['web', 'site', 'internet', 'google'],
            'sistem': ['sistem', 'bilgisayar', 'system', 'info'],
            'kim': ['kim', 'who', 'yourself', 'sen kim'],
            'tarih': ['tarih', 'date', 'takvim', 'calendar'],
            'hava': ['hava', 'weather', 'hava durumu'],
        }
        
        # Metindeki kelimeleri kontrol et
        words = text_lower.split()
        
        for keyword, aliases in command_keywords.items():
            for word in words:
                # Exact match
                if word in aliases:
                    print(f"[OK] Komut buluşturuldu: {keyword}\n")
                    if keyword == 'saat':
                        return self.get_time(text)
                    elif keyword == 'chrome':
                        return self.open_chrome(text)
                    elif keyword == 'dosya':
                        return self.open_file(text)
                    elif keyword == 'web':
                        return self.open_web(text)
                    elif keyword == 'sistem':
                        return self.system_info(text)
                    elif keyword == 'kim':
                        return self.introduce(text)
                    elif keyword == 'tarih':
                        return self.get_date(text)
                    elif keyword == 'hava':
                        return self.get_weather(text)
                
                # Fuzzy match - %80 benzerlik
                if len(word) > 2:
                    for alias in aliases:
                        similarity = SequenceMatcher(None, word, alias).ratio()
                        if similarity > 0.75:
                            print(f"[OK] Benzer komut bulundu: {keyword} (eşleşme: %{int(similarity*100)})\n")
                            if keyword == 'saat':
                                return self.get_time(text)
                            elif keyword == 'chrome':
                                return self.open_chrome(text)
                            elif keyword == 'dosya':
                                return self.open_file(text)
                            elif keyword == 'web':
                                return self.open_web(text)
                            elif keyword == 'sistem':
                                return self.system_info(text)
                            elif keyword == 'kim':
                                return self.introduce(text)
                            elif keyword == 'tarih':
                                return self.get_date(text)
                            elif keyword == 'hava':
                                return self.get_weather(text)
        
        # Bilinmeyen komut
        self.respond_unknown(text)
        return True
    
    def startup_message(self):
        """Başlangıç mesajı"""
        print("\n" + "="*60)
        print(f"[AI] {self.name.upper()} - AI ASISTAN")
        print("="*60)
        print("Merhaba! Ben JARVIS'im. Size yardımcı olabilirim.")
        
        if self.ai_enabled:
            print("[ON] ChatGPT AI Modul: AKTIF")
            ai_status = "ChatGPT destekli yapay zeka sistemi acik."
        else:
            print("[OFF] ChatGPT AI Modul: PASIF")
            ai_status = "Yalnizca temel komutlar mevcut."
        
        print("Komutlar: saat, hava, takvim, dosya, web, sistem, kim, cik")
        print("Veya herhangi bir soruyu sorun!")
        print("="*60 + "\n")
        
        self.speak(f"Merhaba. Ben {self.name}. Size yardimci olmaya hazirim. {ai_status}")
    
    def get_time(self, text=""):
        """Saati söyle"""
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        day = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][now.weekday()]
        
        message = f"Saat şu anda {time_str}, {day}"
        print(f"[AI] {self.name}: {message}\n")
        self.speak(message)
        return True
    
    def get_date(self, text=""):
        """Tarihi söyle"""
        now = datetime.now()
        date_str = now.strftime("%d %B %Y")
        
        message = f"Bugünün tarihi {date_str}"
        print(f"[AI] {self.name}: {message}\n")
        self.speak(message)
        return True
    
    def get_weather(self, text=""):
        """Hava durumu"""
        # Not: Gerçek API kullanmak gerekebilir
        message = "Hava durumu bilgisi şu anda görmek mümkün değil, internet bağlantısı gerekli"
        print(f"[AI] {self.name}: {message}\n")
        self.speak(message)
        return True
    
    def open_file(self, text=""):
        """Dosya/Program aç - masaüstündeki exe ve kısayolları direkt çalıştır"""
        import os
        
        text_lower = text.lower()
        
        # Masaüstü yolu
        desktop_path = os.path.expanduser('~\\Desktop')
        
        # Masaüstündeki dosyaları al
        try:
            files = os.listdir(desktop_path)
        except:
            message = "Masaüstü erişilemedi"
            print(f"[AI] {self.name}: {message}\n")
            self.speak(message)
            return True
        
        # Exe, link ve bat dosyalarını filtrele
        programs = [f for f in files if f.endswith(('.exe', '.lnk', '.bat'))]
        
        # Dosya adlarından program ismini çıkar (uzantısız)
        program_names = {os.path.splitext(f)[0].lower(): f for f in programs}
        
        def get_link_target(lnk_path):
            """Kısayol dosyasının hedefini al"""
            if not HAS_WIN32COM:
                # win32com yoksa lnk dosyasını direk aç
                return lnk_path
            
            try:
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateSCObject(lnk_path)
                target = shortcut.Targetpath
                return target if os.path.exists(target) else lnk_path
            except:
                return lnk_path
        
        # 1. Exact match dene
        for program_name, filename in program_names.items():
            if program_name in text_lower:
                try:
                    file_path = os.path.join(desktop_path, filename)
                    
                    # Eğer lnk ise gerçek hedefi al
                    if filename.endswith('.lnk'):
                        file_path = get_link_target(file_path)
                    
                    # Programı çalıştır
                    subprocess.Popen(file_path)
                    message = f"{program_name.capitalize()} çalıştırılıyor..."
                    print(f"[AI] {self.name}: {message}\n")
                    self.speak(message)
                    return True
                except Exception as e:
                    pass
        
        # 2. Fuzzy match dene (%75 benzerlik)
        words = text_lower.split()
        for word in words:
            for program_name, filename in program_names.items():
                similarity = SequenceMatcher(None, word, program_name).ratio()
                if similarity > 0.75:
                    try:
                        file_path = os.path.join(desktop_path, filename)
                        
                        # Eğer lnk ise gerçek hedefi al
                        if filename.endswith('.lnk'):
                            file_path = get_link_target(file_path)
                        
                        # Programı çalıştır
                        subprocess.Popen(file_path)
                        message = f"{program_name.capitalize()} çalıştırılıyor..."
                        print(f"[AI] {self.name}: {message}\n")
                        self.speak(message)
                        return True
                    except:
                        pass
        
        # Bulunmazsa masaüstü aç
        try:
            os.startfile(desktop_path)
            message = "Masaüstü açılıyor..."
            print(f"[AI] {self.name}: {message}\n")
            self.speak(message)
            return True
        except:
            message = "Program açılamadı"
            print(f"[AI] {self.name}: {message}\n")
            self.speak(message)
            return True
    
    def open_web(self, text=""):
        """Web sitesi aç"""
        if "google" in text.lower():
            webbrowser.open("https://www.google.com")
            message = "Google açılıyor"
        elif "youtube" in text.lower():
            webbrowser.open("https://www.youtube.com")
            message = "YouTube açılıyor"
        else:
            message = "Web sitesini belirtin: Google, YouTube, vb"
        
        print(f"[AI] {self.name}: {message}\n")
        self.speak(message)
        return True
    
    def open_chrome(self, text=""):
        """Chrome tarayıcısı aç"""
        try:
            # Path'ler
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
            
            for path in chrome_paths:
                if os.path.exists(path):
                    subprocess.Popen(path)
                    message = "Chrome tarayıcısı açılıyor"
                    print(f"[AI] {self.name}: {message}\n")
                    self.speak(message)
                    return True
            
            # Fallback
            webbrowser.open("https://www.google.com")
            message = "Chrome tarayıcısı açılıyor"
            print(f"[AI] {self.name}: {message}\n")
            self.speak(message)
            return True
        
        except Exception as e:
            message = f"Chrome açılamadı: {e}"
            print(f"[AI] {self.name}: {message}\n")
            self.speak("Chrome açılamadı")
            return True
    
    def system_info(self, text=""):
        """Bilgisayar bilgisi"""
        import platform
        
        info = f"İşletim Sistemi: {platform.system()} {platform.release()}"
        print(f"[AI] {self.name}: {info}\n")
        self.speak(info)
        return True
    
    def introduce(self, text=""):
        """Kendini tanıt"""
        message = f"Ben {self.name}. Iron Man'ın yapay zeka asistanı benzeri bir AI yardımcısıyım. Size komutlar konusunda yardımcı olabilirim."
        print(f"[AI] {self.name}: {message}\n")
        self.speak(message)
        return True
    
    def greet(self, text=""):
        """Selamlaş"""
        greetings = [
            "Merhaba! Nasıl yardımcı olabilirim?",
            "Selam! Benim mi aradın?",
            "Merhaba! Hoş geldin.",
            "En iyisi dostum, seni görmek güzel!"
        ]
        
        import random
        message = random.choice(greetings)
        print(f"[AI] {self.name}: {message}\n")
        self.speak(message)
        return True
    
    def chat_with_ai(self, text=""):
        """ChatGPT ile yapay zeka sohbeti"""
        if not self.ai_enabled:
            return None
        
        try:
            response = self.ai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.7,
                max_tokens=150
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[ERROR] AI Hatası: {e}")
            return None
    
    def respond_unknown(self, text=""):
        """Bilinmeyen komut - AI'ye yönlendir"""
        # Önce AI'ye sor
        if self.ai_enabled:
            ai_response = self.chat_with_ai(text)
            if ai_response:
                print(f"[AI] {self.name}: {ai_response}\n")
                self.speak(ai_response)
                return True
        
        # AI yoksa fallback
        responses = [
            "Bu komutu anlamadım. Lütfen başka birini deneyin.",
            "Bunu nasıl yapacağımı bilmiyorum.",
            "İnternet bağlantısı gerekebilir.",
            "Tekrar söyler misin?",
        ]
        
        import random
        message = random.choice(responses)
        print(f"[AI] {self.name}: {message}\n")
        self.speak(message)
        return True
    
    def goodbye(self, text=""):
        """Kapan"""
        message = "Hoşça kalın! Tekrar görüşmek dilerim."
        print(f"[AI] {self.name}: {message}\n")
        self.speak(message)
        return False
    
    def run(self):
        """Ana döngü"""
        while True:
            text = self.listen()
            
            if text:
                continue_loop = self.process_command(text)
                
                if not continue_loop:
                    break

def main():
    jarvis = JARVIS(name="JARVIS")
    
    try:
        jarvis.run()
    except KeyboardInterrupt:
        print("\n\n⏹️  Kapatılıyor...")
        jarvis.speak("Sistem kapatılıyor")

if __name__ == "__main__":
    main()
