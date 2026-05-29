import os
import sys
import subprocess
import platform
import httpx
import shutil

async def download_file(url, dest):
    """Baixa um arquivo de atualização, streaming para não travar o event loop."""
    import asyncio
    timeout = httpx.Timeout(connect=10.0, read=300.0, write=None, pool=None)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        try:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                chunks = []
                async for chunk in resp.aiter_bytes(65536):
                    chunks.append(chunk)
            def write_file():
                with open(dest, 'wb') as f:
                    for chunk in chunks:
                        f.write(chunk)
            await asyncio.to_thread(write_file)
            return True
        except Exception as e:
            print(f"Erro no download da atualização: {e}")
            return False

def _clean_subprocess_env():
    """Ambiente sem as variáveis do bootloader do PyInstaller.

    Em modo onefile, o bootloader exporta `_MEIPASS2` (e `_PYI_*` no 6.x)
    apontando para o diretório temporário `_MEI...` deste processo. Se o novo
    executável herdar essas variáveis, ele assume ser o 2º estágio e tenta
    reutilizar a pasta `_MEI...` antiga (que será apagada), causando o erro
    'Failed to load Python DLL ..._MEIxxxx\\python311.dll'. Removê-las força o
    novo processo a extrair uma cópia limpa.
    """
    env = os.environ.copy()
    for key in list(env.keys()):
        if key.startswith("_MEI") or key.startswith("_PYI"):
            env.pop(key, None)
    return env

def apply_update_and_restart(new_file_path):
    """Cria script de substituição, executa e fecha o app atual."""
    current_exe = os.path.abspath(sys.argv[0])
    system = platform.system().lower()
    clean_env = _clean_subprocess_env()

    if system == "windows":
        bat_content = f"""@echo off
timeout /t 4 /nobreak > nul
del /f /q "{current_exe}"
move /y "{new_file_path}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
        bat_path = os.path.join(os.path.dirname(current_exe), "update_helper.bat")
        with open(bat_path, "w") as f:
            f.write(bat_content)

        subprocess.Popen(
            bat_path,
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=clean_env,
        )

    else:
        sh_content = f"""#!/bin/bash
sleep 3
rm -f "{current_exe}"
mv -f "{new_file_path}" "{current_exe}"
chmod +x "{current_exe}"
"{current_exe}" &
rm "$0"
"""
        sh_path = os.path.join(os.path.dirname(current_exe), "update_helper.sh")
        with open(sh_path, "w") as f:
            f.write(sh_content)

        os.chmod(sh_path, 0o755)
        subprocess.Popen(["/bin/bash", sh_path], env=clean_env)

    # os._exit evita que os handlers atexit do PyInstaller deletem _MEI* antes
    # do novo processo terminar de inicializar, prevenindo o erro de DLL.
    os._exit(0)
