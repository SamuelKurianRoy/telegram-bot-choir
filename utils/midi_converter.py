#!/usr/bin/env python3
"""
MIDI to Synthesia-Style Video Converter with Audio
Generates falling notes animation videos from MIDI files WITH AUDIO
FIXED: Correct pitch display in video
"""

import numpy as np
import cv2
from mido import MidiFile
from pathlib import Path
from collections import defaultdict
import subprocess
import os
import tempfile
import shutil

class MidiToVideoWithAudio:
    def __init__(self, midi_path, output_path, width=1920, height=1080, fps=60, 
                 include_audio=True, soundfont_path=None):
        self.midi_path = midi_path
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.include_audio = include_audio
        self.soundfont_path = soundfont_path
        
        # Piano settings - MIDI note 21 = A0, note 108 = C8
        self.min_note = 21  # A0 (MIDI note number 21)
        self.max_note = 108  # C8 (MIDI note number 108)
        self.num_keys = self.max_note - self.min_note + 1
        self.key_width = self.width / self.num_keys
        
        # Animation settings
        self.pixels_per_second = height * 0.6
        self.keyboard_height = 150
        self.fall_zone_height = height - self.keyboard_height
        
        # Colors (BGR format for OpenCV)
        self.bg_color = (20, 20, 20)
        self.white_key_color = (240, 240, 240)
        self.black_key_color = (40, 40, 40)
        self.white_key_pressed = (100, 180, 255)
        self.black_key_pressed = (60, 140, 220)
        
        # Note colors by channel
        self.note_colors = [
            (255, 100, 100),  # Red
            (100, 255, 100),  # Green
            (100, 100, 255),  # Blue
            (255, 255, 100),  # Yellow
            (255, 100, 255),  # Magenta
            (100, 255, 255),  # Cyan
            (255, 180, 100),  # Orange
            (180, 100, 255),  # Purple
        ]
        
    def is_black_key(self, note):
        """
        Check if a piano key is black based on MIDI note number.
        MIDI note numbers mod 12:
          White keys: C=0, D=2, E=4, F=5, G=7, A=9, B=11
          Black keys: C#=1, D#=3, F#=6, G#=8, A#=10
        
        BUG FIX: Must use (note % 12), NOT ((note - self.min_note) % 12)
        The original code was calculating position relative to A0, which
        shifted all black/white assignments incorrectly!
        """
        note_in_octave = note % 12
        # Black keys are at positions 1(C#), 3(D#), 6(F#), 8(G#), 10(A#)
        return note_in_octave in [1, 3, 6, 8, 10]
    
    def get_key_x_position(self, note):
        """
        Get the x position of a key on the keyboard.
        Note: This calculates position relative to the full 88-key range.
        """
        if note < self.min_note or note > self.max_note:
            return None
        key_index = note - self.min_note
        return int(key_index * self.key_width)
    
    def parse_midi(self):
        """Parse MIDI file and extract note events"""
        print(f"Loading MIDI file: {self.midi_path}")
        midi = MidiFile(self.midi_path)
        
        ticks_per_beat = midi.ticks_per_beat
        tempo = 500000
        
        events = []
        active_notes = defaultdict(lambda: defaultdict(dict))
        current_tick = 0
        current_time = 0.0
        
        for track_idx, track in enumerate(midi.tracks):
            current_tick = 0
            current_time = 0.0
            
            for msg in track:
                current_tick += msg.time
                current_time += (msg.time / ticks_per_beat) * (tempo / 1000000.0)
                
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                elif msg.type == 'note_on' and msg.velocity > 0:
                    # BUG FIX: If this note is already active, finish it first!
                    # This handles repeated notes (same note played again before release)
                    if msg.note in active_notes[track_idx]:
                        note_info = active_notes[track_idx][msg.note]
                        # Add a visible gap (0.05 seconds) before the new note for visual separation
                        gap_time = 0.05
                        events.append({
                            'note': msg.note,
                            'start_time': note_info['start_time'],
                            'end_time': current_time - gap_time,
                            'duration': (current_time - gap_time) - note_info['start_time'],
                            'velocity': note_info['velocity'],
                            'channel': note_info['channel']
                        })
                    
                    # Now start the new note
                    active_notes[track_idx][msg.note] = {
                        'start_time': current_time,
                        'velocity': msg.velocity,
                        'channel': msg.channel
                    }
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if msg.note in active_notes[track_idx]:
                        note_info = active_notes[track_idx][msg.note]
                        events.append({
                            'note': msg.note,
                            'start_time': note_info['start_time'],
                            'end_time': current_time,
                            'duration': current_time - note_info['start_time'],
                            'velocity': note_info['velocity'],
                            'channel': note_info['channel']
                        })
                        del active_notes[track_idx][msg.note]
        
        events.sort(key=lambda x: x['start_time'])
        
        if not events:
            print("Error: No note events found in MIDI file!")
            return None
        
        self.total_duration = max(e['end_time'] for e in events) + 2.0
        
        # Debug: Show note range to verify correct pitch
        note_numbers = [e['note'] for e in events]
        min_note_played = min(note_numbers)
        max_note_played = max(note_numbers)
        
        # FIXED: Correct MIDI note to name conversion
        # In MIDI: C4 (middle C) = note 60
        # Formula: octave = (note // 12) - 1, so note 60 -> octave 4
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        def note_to_name(note_num):
            """Convert MIDI note number to note name with octave"""
            octave = (note_num // 12) - 1
            note_name = note_names[note_num % 12]
            return f"{note_name}{octave}"
        
        print(f"Found {len(events)} notes, total duration: {self.total_duration:.2f} seconds")
        print(f"Note range: {note_to_name(min_note_played)} (MIDI {min_note_played}) to {note_to_name(max_note_played)} (MIDI {max_note_played})")
        print(f"Keyboard range: {note_to_name(self.min_note)} (MIDI {self.min_note}) to {note_to_name(self.max_note)} (MIDI {self.max_note})")
        print(f"")
        print(f"Verification: MIDI note 60 = {note_to_name(60)} (should be C4/Middle C)")
        print(f"Verification: MIDI note 69 = {note_to_name(69)} (should be A4/440 Hz)")
        
        return events
    
    def draw_keyboard(self, frame, pressed_notes):
        """Draw a realistic 3D-style piano keyboard at the bottom"""
        keyboard_y = self.height - self.keyboard_height
        
        # Draw shadow under keyboard for depth
        shadow_height = 15
        for i in range(shadow_height):
            alpha = 1.0 - (i / shadow_height)
            shadow_color = tuple(int(c * (1 - alpha * 0.5)) for c in self.bg_color)
            cv2.line(frame, 
                    (0, keyboard_y - shadow_height + i), 
                    (self.width, keyboard_y - shadow_height + i),
                    shadow_color, 1)
        
        # Draw white keys with 3D effect
        for note in range(self.min_note, self.max_note + 1):
            if not self.is_black_key(note):
                x = self.get_key_x_position(note)
                
                if note in pressed_notes:
                    # Pressed key - darker with gradient
                    base_color = self.white_key_pressed
                    # Top part darker (pressed down)
                    top_color = tuple(max(0, c - 50) for c in base_color)
                    bottom_color = base_color
                else:
                    # Unpressed key - white with subtle gradient
                    top_color = (255, 255, 255)
                    bottom_color = (230, 230, 230)
                
                # Draw gradient
                key_rect_y1 = keyboard_y
                key_rect_y2 = self.height
                for y in range(key_rect_y1, key_rect_y2):
                    ratio = (y - key_rect_y1) / (key_rect_y2 - key_rect_y1)
                    color = tuple(int(top_color[i] * (1 - ratio) + bottom_color[i] * ratio) 
                                for i in range(3))
                    cv2.line(frame, 
                           (x, y), 
                           (x + int(self.key_width), y),
                           color, 1)
                
                # Draw key borders
                cv2.rectangle(frame, 
                            (x, keyboard_y), 
                            (x + int(self.key_width), self.height),
                            (80, 80, 80), 2)
                
                # Add highlight on left edge for 3D effect
                if not note in pressed_notes:
                    cv2.line(frame, 
                           (x + 2, keyboard_y + 2), 
                           (x + 2, self.height - 2),
                           (255, 255, 255), 1)
        
        # Draw black keys on top with enhanced 3D effect
        black_key_width = int(self.key_width * 0.6)
        black_key_height = int(self.keyboard_height * 0.58)  # 58% of white key height (more realistic)
        
        for note in range(self.min_note, self.max_note + 1):
            if self.is_black_key(note):
                x = self.get_key_x_position(note)
                x_center = x + int(self.key_width / 2) - black_key_width // 2
                
                if note in pressed_notes:
                    # Pressed black key
                    base_color = self.black_key_pressed
                    top_color = tuple(max(0, c - 30) for c in base_color)
                    bottom_color = base_color
                else:
                    # Unpressed black key with gradient
                    top_color = (60, 60, 60)
                    bottom_color = (20, 20, 20)
                
                # Draw gradient for black key
                key_rect_y1 = keyboard_y
                key_rect_y2 = keyboard_y + black_key_height
                for y in range(key_rect_y1, key_rect_y2):
                    ratio = (y - key_rect_y1) / (key_rect_y2 - key_rect_y1)
                    color = tuple(int(top_color[i] * (1 - ratio) + bottom_color[i] * ratio) 
                                for i in range(3))
                    cv2.line(frame, 
                           (x_center, y), 
                           (x_center + black_key_width, y),
                           color, 1)
                
                # Draw black key border
                cv2.rectangle(frame,
                            (x_center, keyboard_y),
                            (x_center + black_key_width, keyboard_y + black_key_height),
                            (10, 10, 10), 2)
                
                # Add highlight on top-left for 3D effect
                if not note in pressed_notes:
                    cv2.line(frame, 
                           (x_center + 2, keyboard_y + 2), 
                           (x_center + 2, keyboard_y + black_key_height // 3),
                           (100, 100, 100), 1)
                
                # Add shadow on the right side
                shadow_x = x_center + black_key_width
                for i in range(4):
                    cv2.line(frame,
                           (shadow_x + i, keyboard_y),
                           (shadow_x + i, keyboard_y + black_key_height),
                           (max(0, 20 - i * 5), max(0, 20 - i * 5), max(0, 20 - i * 5)),
                           1)
    
    def draw_falling_note(self, frame, note_event, current_time):
        """Draw a falling note with 3D effect"""
        note = note_event['note']
        start_time = note_event['start_time']
        end_time = note_event['end_time']
        duration = note_event['duration']
        
        if note < self.min_note or note > self.max_note:
            return
        
        keyboard_y = self.height - self.keyboard_height
        time_to_hit = start_time - current_time
        note_bottom_y = keyboard_y - (time_to_hit * self.pixels_per_second)
        note_top_y = note_bottom_y - (duration * self.pixels_per_second)
        
        if note_top_y > self.height or note_bottom_y < 0:
            return
        
        base_color = self.note_colors[note_event['channel'] % len(self.note_colors)]
        x = self.get_key_x_position(note)
        note_width = int(self.key_width * 0.85)
        x_offset = int((self.key_width - note_width) / 2)
        
        if self.is_black_key(note):
            note_width = int(self.key_width * 0.5)
            x_offset = int((self.key_width - note_width) / 2)
        
        x1 = x + x_offset
        x2 = x1 + note_width
        y1 = max(0, int(note_top_y))
        y2 = min(keyboard_y, int(note_bottom_y))
        
        if y2 > y1:
            # Draw shadow first (offset to the right and down)
            shadow_offset = 3
            shadow_color = (10, 10, 10)
            cv2.rectangle(frame, 
                         (x1 + shadow_offset, y1 + shadow_offset), 
                         (x2 + shadow_offset, y2 + shadow_offset), 
                         shadow_color, -1)
            
            # Draw gradient on the note for 3D effect
            for y in range(y1, y2):
                # Calculate gradient from left to right
                gradient_colors = []
                for x_pos in range(x1, x2):
                    ratio = (x_pos - x1) / max(1, (x2 - x1))
                    # Darker on left, lighter on right
                    color = tuple(int(base_color[i] * (0.7 + ratio * 0.3)) for i in range(3))
                    gradient_colors.append(color)
                
                # Draw the line with gradient
                for i, x_pos in enumerate(range(x1, x2)):
                    frame[y, x_pos] = gradient_colors[i]
            
            # Add bright highlight on the top-left edge
            highlight_color = tuple(min(255, c + 80) for c in base_color)
            cv2.line(frame, (x1 + 2, y1), (x1 + 2, y2), highlight_color, 2)
            cv2.line(frame, (x1, y1 + 2), (x2, y1 + 2), highlight_color, 2)
            
            # Draw border
            border_color = tuple(min(255, c + 40) for c in base_color)
            cv2.rectangle(frame, (x1, y1), (x2, y2), border_color, 2)
            
            # Add glow effect when note is about to hit
            if time_to_hit < 0.5 and time_to_hit > -0.1:
                glow_intensity = int(100 * (1 - abs(time_to_hit) / 0.5))
                glow_color = tuple(min(255, c + glow_intensity) for c in base_color)
                cv2.rectangle(frame, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), glow_color, 1)
                cv2.rectangle(frame, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), glow_color, 1)
    
    def convert_midi_to_audio(self):
        """Convert MIDI to audio using FluidSynth or Timidity"""
        print("\n=== Converting MIDI to Audio ===")
        
        audio_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        
        # Try FluidSynth first (better quality) - Cloud deployment
        try:
            # Check if fluidsynth is available
            check_result = subprocess.run(['which', 'fluidsynth'], capture_output=True, text=True)
            if check_result.returncode != 0:
                raise FileNotFoundError("FluidSynth not found")
            
            cmd = ['fluidsynth', '-ni']
            
            # Try to find soundfonts (cloud deployment paths)
            default_soundfonts = [
                '/usr/share/sounds/sf2/FluidR3_GM.sf2',
                '/usr/share/sounds/sf2/default.sf2',
                '/usr/share/soundfonts/default.sf2',
                '/usr/share/soundfonts/FluidR3_GM.sf2',
                '/app/.apt/usr/share/sounds/sf2/FluidR3_GM.sf2',  # Streamlit Cloud path
            ]
            
            soundfont_found = False
            if self.soundfont_path and os.path.exists(self.soundfont_path):
                cmd.append(self.soundfont_path)
                soundfont_found = True
                print(f"Using custom soundfont: {self.soundfont_path}")
            else:
                for sf in default_soundfonts:
                    if os.path.exists(sf):
                        cmd.append(sf)
                        soundfont_found = True
                        print(f"Using soundfont: {sf}")
                        break
            
            if not soundfont_found:
                print("Warning: No soundfont found, using FluidSynth default")
            
            # Set parameters optimized for cloud deployment
            cmd.extend([
                self.midi_path,
                '-F', audio_file,
                '-r', '44100',  # 44.1kHz sample rate (smaller than 48kHz)
                '-g', '0.8',    # Slightly lower gain to prevent clipping
                '-T', 'wav'     # Output format
            ])
            
            print("Trying FluidSynth...")
            # Add timeout for cloud deployment (max 120 seconds for audio generation)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0 and os.path.exists(audio_file) and os.path.getsize(audio_file) > 0:
                print("✓ Audio generated with FluidSynth")
                return audio_file
            else:
                print(f"FluidSynth failed with return code {result.returncode}")
                if result.stderr:
                    print(f"Error: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print("FluidSynth timed out (file too long)")
        except FileNotFoundError:
            print("FluidSynth not found, trying Timidity...")
        except Exception as e:
            print(f"FluidSynth failed: {e}")
        
        # Try Timidity as fallback
        try:
            print("Trying Timidity...")
            cmd = ['timidity', self.midi_path, '-Ow', '-o', audio_file]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0 and os.path.exists(audio_file) and os.path.getsize(audio_file) > 0:
                print("✓ Audio generated with Timidity")
                return audio_file
        except subprocess.TimeoutExpired:
            print("Timidity timed out")
        except FileNotFoundError:
            print("Timidity not found")
        except Exception as e:
            print(f"Timidity failed: {e}")
        
        print("\n⚠️  Warning: Could not generate audio")
        print("Generating video without audio...")
        
        # Clean up failed audio file
        if os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except:
                pass
        
        return None
    
    def combine_video_audio(self, video_file, audio_file):
        """Combine video and audio using FFmpeg"""
        print("\n=== Combining Video and Audio ===")
        
        try:
            # Check if ffmpeg is available
            check_result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
            if check_result.returncode != 0:
                raise FileNotFoundError("FFmpeg not found")
        except FileNotFoundError:
            print("⚠️  FFmpeg not found. Cannot combine video and audio.")
            print(f"Video saved without audio: {video_file}")
            return False
        
        temp_output = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
        
        cmd = [
            'ffmpeg', '-y',
            '-i', video_file,
            '-i', audio_file,
            '-c:v', 'copy',           # Copy video stream as-is
            '-c:a', 'aac',            # Encode audio as AAC
            '-b:a', '128k',           # Audio bitrate (reduced for smaller file size)
            '-ar', '44100',           # Audio sample rate - match audio generation
            '-ac', '2',               # Stereo audio
            '-shortest',              # End when shortest stream ends
            '-loglevel', 'error',     # Only show errors
            temp_output
        ]
        
        print("Running FFmpeg...")
        try:
            # Add timeout for cloud deployment
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            
            if result.returncode == 0 and os.path.exists(temp_output):
                # Replace original video with combined version
                # Use shutil.move instead of os.replace to handle cross-device moves
                shutil.move(temp_output, self.output_path)
                # Clean up temporary files
                if os.path.exists(video_file) and video_file != self.output_path:
                    os.remove(video_file)
                if os.path.exists(audio_file):
                    os.remove(audio_file)
                print("✓ Video and audio combined successfully")
                return True
            else:
                print(f"✗ FFmpeg failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            print("✗ FFmpeg timed out during combination")
            return False
        except Exception as e:
            print(f"✗ FFmpeg error: {e}")
            return False
    
    def generate_video(self, progress_callback=None):
        """Generate the complete video with audio
        
        Args:
            progress_callback: Optional callback function(current_frame, total_frames, message)
        """
        events = self.parse_midi()
        if events is None:
            return False
        
        # Cloud deployment safety check: Limit processing time for very long songs
        max_duration = 600  # 10 minutes max (10 * 60 seconds)
        if self.total_duration > max_duration:
            print(f"⚠️  Warning: Song duration ({self.total_duration:.1f}s) exceeds maximum ({max_duration}s)")
            print("Processing will be limited to prevent resource exhaustion on cloud deployment")
            # Truncate to max duration
            self.total_duration = max_duration
            # Filter events to max duration
            events = [e for e in events if e['start_time'] < max_duration]
            if not events:
                print("Error: No events within duration limit!")
                return False
        
        # Generate audio first if requested
        audio_file = None
        if self.include_audio:
            audio_file = self.convert_midi_to_audio()
        
        # Determine video file path
        if audio_file:
            temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
            video_output = temp_video
        else:
            video_output = self.output_path
        
        print(f"\n=== Generating Video ===")
        print(f"Resolution: {self.width}x{self.height} @ {self.fps} FPS")
        print(f"Estimated duration: {self.total_duration:.2f}s")
        
        # Setup video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(video_output, fourcc, self.fps, (self.width, self.height))
        
        if not out.isOpened():
            print("Error: Could not open video writer!")
            return False
        
        total_frames = int(self.total_duration * self.fps)
        
        # Cloud deployment: Report estimated processing time
        estimated_time = total_frames / self.fps * 0.5  # Rough estimate: 0.5 seconds per second of video
        print(f"Estimated processing time: {estimated_time:.1f} seconds")
        
        for frame_num in range(total_frames):
            current_time = frame_num / self.fps
            
            # Create frame
            frame = np.full((self.height, self.width, 3), self.bg_color, dtype=np.uint8)
            
            # Find currently pressed notes
            pressed_notes = set()
            for event in events:
                if event['start_time'] <= current_time <= event['end_time']:
                    pressed_notes.add(event['note'])
            
            # Draw falling notes
            for event in events:
                if event['start_time'] - 3.0 <= current_time <= event['end_time']:
                    self.draw_falling_note(frame, event, current_time)
            
            # Draw keyboard
            self.draw_keyboard(frame, pressed_notes)
            
            # Add timestamp
            timestamp_text = f"Time: {current_time:.2f}s / {self.total_duration:.2f}s"
            cv2.putText(frame, timestamp_text, (20, 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
            
            # Add watermark in bottom right corner
            watermark_text = "Created by Samuel Kurian Roy"
            watermark_size = cv2.getTextSize(watermark_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            watermark_x = self.width - watermark_size[0] - 20
            watermark_y = self.height - 20
            # Add semi-transparent background for watermark
            overlay = frame.copy()
            cv2.rectangle(overlay, 
                         (watermark_x - 10, watermark_y - watermark_size[1] - 10),
                         (watermark_x + watermark_size[0] + 10, watermark_y + 10),
                         (30, 30, 30), -1)
            cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
            cv2.putText(frame, watermark_text, (watermark_x, watermark_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 2)
            
            # Write frame
            out.write(frame)
            
            # Progress callback
            if progress_callback and (frame_num % (self.fps * 5) == 0 or frame_num == total_frames - 1):
                progress = (frame_num + 1) / total_frames * 100
                progress_callback(frame_num + 1, total_frames, f"Progress: {progress:.1f}%")
            
            # Progress indicator
            if frame_num % (self.fps * 5) == 0 or frame_num == total_frames - 1:
                progress = (frame_num + 1) / total_frames * 100
                print(f"Progress: {progress:.1f}% ({frame_num + 1}/{total_frames} frames)")
        
        out.release()
        print(f"✓ Video generated")
        
        # Combine with audio if available
        if audio_file:
            success = self.combine_video_audio(video_output, audio_file)
            if not success and os.path.exists(video_output):
                # If combining failed, just use video without audio
                shutil.move(video_output, self.output_path)
        
        print(f"\n✓ Final output: {self.output_path}")
        return True


def convert_midi_to_video(midi_path, output_path, width=1280, height=720, fps=30, 
                          include_audio=True, progress_callback=None):
    """
    Convert a MIDI file to a Synthesia-style video
    
    Args:
        midi_path: Path to input MIDI file
        output_path: Path for output video file
        width: Video width in pixels (default: 1280)
        height: Video height in pixels (default: 720)
        fps: Frames per second (default: 30)
        include_audio: Whether to include audio (default: True)
        progress_callback: Optional callback function(current_frame, total_frames, message)
    
    Returns:
        bool: True if successful, False otherwise
    """
    converter = MidiToVideoWithAudio(
        midi_path, 
        output_path,
        width=width,
        height=height,
        fps=fps,
        include_audio=include_audio
    )
    
    return converter.generate_video(progress_callback=progress_callback)
