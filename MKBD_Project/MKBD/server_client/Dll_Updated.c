#include <stdio.h>
#include <stdlib.h>
#include <winsock2.h>
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <ctype.h>
#include <time.h>

#pragma comment(lib, "ws2_32.lib")

// DLL function signature
typedef int (__stdcall *DiagKeyFunc)(
    uint8_t* seed,
    size_t seedSize,
    int securityLevel,
    const char* variant,
    uint8_t* key,
    size_t maxKeySize,
    DWORD* actualSize
);

// Constants
#define PORT 5005
#define BUFFER_SIZE 1024
#define MAX_SEED_SIZE 8
#define MAX_KEY_SIZE 8

// Print timestamped log
void print_timestamp(const char* message) {
    FILETIME ft;
    ULARGE_INTEGER uli;

    // Use high-precision timestamp if available (Windows 8+)
    HMODULE hKernel32 = GetModuleHandle("kernel32.dll");
    if (hKernel32) {
        FARPROC pGetPreciseTime = GetProcAddress(hKernel32, "GetSystemTimePreciseAsFileTime");
        if (pGetPreciseTime) {
            ((void(WINAPI*)(LPFILETIME))pGetPreciseTime)(&ft);
        } else {
            GetSystemTimeAsFileTime(&ft);
        }
    }

    uli.LowPart = ft.dwLowDateTime;
    uli.HighPart = ft.dwHighDateTime;

    // Convert to microseconds since Windows epoch (1601)
    uint64_t microseconds = uli.QuadPart / 10;

    // Convert to seconds and microseconds
    time_t seconds = (time_t)((microseconds - 11644473600000000ULL) / 1000000);
    int micros = (int)((microseconds - 11644473600000000ULL) % 1000000);

    struct tm t;
    localtime_s(&t, &seconds);

    char time_str[64];
    strftime(time_str, sizeof(time_str), "%Y-%m-%d %H:%M:%S", &t);
    printf("[%s.%06d] %s\n", time_str, micros, message);
}

// Convert hex string to byte array
int hexstr_to_bytes(const char* hexstr, uint8_t* byte_array, size_t max_len) {
    size_t count = 0;
    while (*hexstr && *(hexstr + 1) && count < max_len) {
        while (*hexstr == ' ') hexstr++; // Skip spaces
        if (!isxdigit(hexstr[0]) || !isxdigit(hexstr[1])) break;
        sscanf(hexstr, "%2hhx", &byte_array[count]);
        hexstr += 2;
        count++;
    }
    return count;
}

int main() {
    WSADATA wsa;
    SOCKET sock;
    struct sockaddr_in server, client;
    int client_len = sizeof(client);
    char buffer[BUFFER_SIZE];

    // Load DLL
    HINSTANCE hDLL = LoadLibrary("C:\\Users\\Namdev\\Desktop\\BDC_RAS_PI\\AY_BDC_SMK_R01 (1)\\AY_CANoe Configuration\\CDD\\HKMC_AdvancedSeedKey_Win32 (1)");
    if (hDLL == NULL) {
        printf("Failed to load DLL. Error code: %lu\n", GetLastError());
        return 1;
    }

    // Get DLL function
    DiagKeyFunc GenerateKey = (DiagKeyFunc)GetProcAddress(hDLL, "GenerateKeyEx");
    if (GenerateKey == NULL) {
        printf("Failed to locate GenerateKeyEx function. Error code: %lu\n", GetLastError());
        FreeLibrary(hDLL);
        return 1;
    }

    // Initialize Winsock
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        printf("WSAStartup failed: %d\n", WSAGetLastError());
        FreeLibrary(hDLL);
        return 1;
    }

    // Create socket
    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock == INVALID_SOCKET) {
        printf("Socket creation failed: %d\n", WSAGetLastError());
        WSACleanup();
        FreeLibrary(hDLL);
        return 1;
    }

    // Bind
    server.sin_family = AF_INET;
    server.sin_addr.s_addr = INADDR_ANY;
    server.sin_port = htons(PORT);
    if (bind(sock, (struct sockaddr*)&server, sizeof(server)) == SOCKET_ERROR) {
        printf("Bind failed: %d\n", WSAGetLastError());
        closesocket(sock);
        WSACleanup();
        FreeLibrary(hDLL);
        return 1;
    }

    print_timestamp("Server is listening...");

    // Main loop
    while (1) {
        memset(buffer, 0, BUFFER_SIZE);
        int recv_len = recvfrom(sock, buffer, BUFFER_SIZE - 1, 0, (struct sockaddr*)&client, &client_len);
        if (recv_len == SOCKET_ERROR) {
            printf("recvfrom() failed: %d\n", WSAGetLastError());
            continue;
        }

        buffer[recv_len] = '\0'; // Null-terminate

        printf("\n[DEBUG] Packet received: %d bytes\n", recv_len);
        print_timestamp("Seed received");
        printf("Raw received seed string: %s\n", buffer);

        // Convert seed to byte array
        uint8_t seedArray[MAX_SEED_SIZE] = {0};
        int seedArraySize = hexstr_to_bytes(buffer, seedArray, MAX_SEED_SIZE);
        if (seedArraySize <= 0) {
            printf("[ERROR] Invalid seed format received.\n");
            const char* failMsg = "Invalid seed format";
            sendto(sock, failMsg, strlen(failMsg), 0, (struct sockaddr*)&client, client_len);
            continue;
        }

        // Call DLL to generate key
        int securityLevel = 0x0B;
        char variant[200] = "Common";
        uint8_t keyArray[MAX_KEY_SIZE] = {0};
        DWORD actualSize = 0;

        printf("[INFO] Generating key using DLL...\n");
        int result = GenerateKey(seedArray, seedArraySize, securityLevel, variant, keyArray, MAX_KEY_SIZE, &actualSize);
        printf("[DEBUG] DLL returned result: %d\n", result);

        if (result == 0) {
            printf("[SUCCESS] Key generated: ");
            for (DWORD i = 0; i < actualSize; i++) {
                printf("%02X ", keyArray[i]);
            }
            printf("\n");

            sendto(sock, keyArray, actualSize, 0, (struct sockaddr*)&client, client_len);
            print_timestamp("Key sent");
        } else {
            printf("[ERROR] Key generation failed (code: %d)\n", result);
            const char* failMsg = "Key generation failed";
            sendto(sock, failMsg, strlen(failMsg), 0, (struct sockaddr*)&client, client_len);
        }
    }

    // Cleanup (never reached in infinite loop, but good practice)
    print_timestamp("Server shutting down.");
    closesocket(sock);
    WSACleanup();
    FreeLibrary(hDLL);
    return 0;
}
