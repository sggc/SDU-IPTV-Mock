#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
import multiprocessing
from multiprocessing import Process, Queue, Value, Array
from Crypto.Cipher import DES
from Crypto.Util.Padding import unpad
import ctypes

AUTHENTICATOR = ""

def decrypt_des(key_int, cipher_bytes):
    try:
        key_str = f"{key_int:08d}"
        key = key_str.encode('ascii')
        cipher = DES.new(key, DES.MODE_ECB)
        decrypted = cipher.decrypt(cipher_bytes)
        pad_len = decrypted[-1]
        if pad_len > 8 or pad_len == 0:
            return None
        plaintext = decrypted[:-pad_len].decode('utf-8', errors='ignore')
        return plaintext
    except:
        return None

def validate_plaintext(plaintext):
    if not plaintext:
        return False, None
    
    parts = plaintext.split('$')
    
    if len(parts) < 7:
        return False, None
    
    platform = parts[-1] if parts[-1] in ['CTC', 'CU'] else None
    if not platform:
        return False, None
    
    if len(parts) >= 3 and not parts[2].isdigit():
        return False, None
    
    if len(parts[0]) != 8 or not parts[0].isdigit():
        return False, None
    
    return True, parts

def crack_worker(worker_id, start, end, cipher_bytes, result_queue, checked_count, stop_flag):
    local_checked = 0
    report_interval = 10000
    
    for i in range(start, end):
        if stop_flag.value:
            return
        
        plaintext = decrypt_des(i, cipher_bytes)
        valid, parts = validate_plaintext(plaintext)
        
        if valid:
            key_str = f"{i:08d}"
            result_queue.put((key_str, plaintext, parts))
            print(f"\n>>> 找到密钥: {key_str} | {plaintext[:50]}...")
        
        local_checked += 1
        
        if local_checked >= report_interval:
            checked_count[worker_id] += local_checked
            local_checked = 0
    
    checked_count[worker_id] += local_checked

def crack_all_keys(authenticator, num_workers=None):
    if num_workers is None:
        num_workers = multiprocessing.cpu_count()
        if num_workers < 8:
            num_workers = 8
    
    print("=" * 80)
    print("穷举所有可能的密钥")
    print("=" * 80)
    print(f"Authenticator: {authenticator[:60]}...")
    print(f"密钥空间: 00000000 - 99999999 (共1亿个)")
    print(f"工作进程数: {num_workers}")
    print("=" * 80)
    print()
    
    cipher_bytes = bytes.fromhex(authenticator)
    
    result_queue = Queue()
    stop_flag = Value(ctypes.c_int, 0)
    
    checked_count = Array(ctypes.c_longlong, num_workers)
    for i in range(num_workers):
        checked_count[i] = 0
    
    total_keys = 100000000
    chunk_size = total_keys // num_workers
    
    workers = []
    for i in range(num_workers):
        start = i * chunk_size
        end = start + chunk_size if i < num_workers - 1 else total_keys
        
        p = Process(
            target=crack_worker,
            args=(i, start, end, cipher_bytes, result_queue, checked_count, stop_flag)
        )
        workers.append(p)
    
    start_time = time.time()
    for p in workers:
        p.start()
    
    last_report_time = start_time
    found_keys = []
    
    try:
        while True:
            while not result_queue.empty():
                try:
                    result = result_queue.get_nowait()
                    found_keys.append(result)
                except:
                    break
            
            total_checked = sum(checked_count[i] for i in range(num_workers))
            
            all_done = all(not p.is_alive() for p in workers)
            
            current_time = time.time()
            if current_time - last_report_time >= 0.5 or all_done:  
                elapsed = current_time - start_time
                speed = total_checked / elapsed if elapsed > 0 else 0
                progress_percent = min((total_checked / total_keys) * 100, 100)
                
                if speed > 0 and not all_done:
                    remaining_keys = total_keys - total_checked
                    remaining_time = remaining_keys / speed if remaining_keys > 0 else 0
                else:
                    remaining_time = 0
                
                bar_length = 50
                filled_length = int(bar_length * progress_percent / 100)
                bar = '#' * filled_length + '-' * (bar_length - filled_length)
                
                print(f"\r[{bar}] {progress_percent:5.2f}% | "
                      f"{total_checked:10d}/{total_keys} | "
                      f"{speed:8.0f} keys/s | "
                      f"已用: {elapsed:5.0f}s | "
                      f"剩余: {remaining_time:5.0f}s | "
                      f"找到: {len(found_keys)}个密钥", end='', flush=True)
                
                last_report_time = current_time
            
            if all_done:
                break
            
            time.sleep(0.05)
    
    except KeyboardInterrupt:
        print("\n\n用户中断...")
        stop_flag.value = 1
        for p in workers:
            p.terminate()
        for p in workers:
            p.join(timeout=1)
    
    print()
    
    for p in workers:
        p.join(timeout=1)
    
    while not result_queue.empty():
        try:
            result = result_queue.get_nowait()
            found_keys.append(result)
        except:
            break
    
    return found_keys

def analyze_keys(found_keys):
    print()
    print("=" * 80)
    print(f"找到 {len(found_keys)} 个可能的密钥")
    print("=" * 80)
    print()
    
    if not found_keys:
        print("未找到任何密钥")
        return
    
    found_keys.sort(key=lambda x: x[0])
    
    print("密钥列表:")
    print("-" * 80)
    
    for i, (key, plaintext, parts) in enumerate(found_keys):
        print(f"[{i+1}] 密钥: {key}")
        print(f"    Random: {parts[0]}")
        print(f"    UserID: {parts[2]}")
        print(f"    Platform: {parts[-1]}")
        print()

def save_results(found_keys, filename="found_keys.txt"):
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"找到 {len(found_keys)} 个可能的密钥\n")
        f.write("=" * 80 + "\n\n")
        
        for i, (key, plaintext, parts) in enumerate(found_keys):
            f.write(f"[{i+1}] 密钥: {key}\n")
            f.write(f"    明文: {plaintext}\n")
            f.write(f"    Random: {parts[0]}\n")
            f.write(f"    UserID: {parts[2]}\n")
            f.write(f"    Platform: {parts[-1]}\n")
            f.write("\n")
    
    print(f"结果已保存到: {filename}")

def main():
    print()
    print("=" * 80)
    print("密钥穷举工具")
    print("=" * 80)
    print()
    
    found_keys = crack_all_keys(AUTHENTICATOR)
    
    analyze_keys(found_keys)
    
    if found_keys:
        save_results(found_keys)
    
    print("=" * 80)
    print("完成")
    print("=" * 80)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n按回车键退出...")
    input()