"""
Cihaz secim katmani: CUDA / XPU / CPU -- makineden bagimsiz.

AMAC: ayni kod NVIDIA'li makinede CUDA, Intel'li makinede XPU, hicbiri
yoksa CPU ile calissin. Kod hicbir yerde "xpu" yazmasin.

TASARIMIN EN ONEMLI KURALI -- IMPORT SIRASINDA SORU SORULMAZ.
  Bu modul notebook'ta, pytest'te, cron'da ve ileride FastAPI surecinde
  import edilecek. Bunlarin hicbirinde stdin yok. Import sirasinda input()
  cagiran bir kutuphane, sunucuyu sessizce kilitler -- hata bile vermez,
  sadece ASILI KALIR. Bu yuzden:

      soru SADECE acikca istendiginde ve SADECE gercek bir terminal varsa
      sorulur. Diger her durumda otomatik secim yapilir.

COZUM SIRASI (ustteki kazanir):
  1. Fonksiyona verilen acik deger      select_device("cuda")
  2. Ortam degiskeni                    SPP_DEVICE=cpu
  3. Bu surecte daha once secilmis olan  (bir kez sorulur, hatirlanir)
  4. Interaktif soru                     ask=True VE gercek terminal varsa
  5. Otomatik: cuda > xpu > cpu

KULLANIM (ileride script'e gecince):
    from model.device import select_device
    dev = select_device(ask=True)     # terminalde sorar, notebook'ta sormaz

    # ya da hic sormadan:
    dev = select_device()             # en iyisini secer

    # tek seferlik zorlamak icin:
    SPP_DEVICE=cpu python tests/run_hybrid.py

Cihaz listesini gormek icin:
    python -m model.device
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass

import torch

log = logging.getLogger(__name__)

ENV_VAR = "SPP_DEVICE"

# Otomatik secimde tercih sirasi. Hizlidan yavasa.
PREFERENCE = ("cuda", "xpu", "mps", "cpu")

# Surec boyunca hatirlanan secim. Bir kez sorulur, bir daha sorulmaz.
_selected: torch.device | None = None


# --------------------------------------------------------------------- bilgi
@dataclass(frozen=True)
class DeviceInfo:
    kind: str                 # "cuda" | "xpu" | "mps" | "cpu"
    index: int                # cihaz sirasi (cpu icin 0)
    name: str                 # insan okuyacak isim
    total_memory: int | None  # bayt; bilinmiyorsa None

    @property
    def torch_device(self) -> torch.device:
        if self.kind == "cpu":
            return torch.device("cpu")
        return torch.device(f"{self.kind}:{self.index}")

    @property
    def spec(self) -> str:
        return "cpu" if self.kind == "cpu" else f"{self.kind}:{self.index}"

    def __str__(self) -> str:
        mem = (
            f"  {self.total_memory / 1024**3:.1f} GB"
            if self.total_memory else ""
        )
        return f"{self.spec:10} {self.name}{mem}"


def _cuda_devices() -> list[DeviceInfo]:
    if not torch.cuda.is_available():
        return []
    out = []
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        out.append(DeviceInfo("cuda", i, p.name, getattr(p, "total_memory", None)))
    return out


def _xpu_devices() -> list[DeviceInfo]:
    # hasattr: torch'un CPU-only surumlerinde torch.xpu HIC YOK.
    if not (hasattr(torch, "xpu") and torch.xpu.is_available()):
        return []
    out = []
    for i in range(torch.xpu.device_count()):
        try:
            p = torch.xpu.get_device_properties(i)
            name = getattr(p, "name", f"Intel XPU {i}")
            mem = getattr(p, "total_memory", None)
        except Exception:  # noqa: BLE001 -- surum farklari, bilgi sart degil
            name, mem = f"Intel XPU {i}", None
        out.append(DeviceInfo("xpu", i, name, mem))
    return out


def _mps_devices() -> list[DeviceInfo]:
    # Apple Silicon. Simdilik test edilmedi ama kapiyi acik birakiyoruz.
    mps = getattr(torch.backends, "mps", None)
    if mps is None or not mps.is_available():
        return []
    return [DeviceInfo("mps", 0, "Apple Silicon GPU (MPS)", None)]


def available_devices() -> list[DeviceInfo]:
    """
    Bu makinede kullanilabilir cihazlar, tercih sirasinda.
    CPU HER ZAMAN listede ve HER ZAMAN sonuncudur -- geri donus yolu.
    """
    devs = _cuda_devices() + _xpu_devices() + _mps_devices()
    devs.append(DeviceInfo("cpu", 0, _cpu_name(), None))
    return devs


def _cpu_name() -> str:
    import platform

    return platform.processor() or platform.machine() or "CPU"


def best_device() -> DeviceInfo:
    """Otomatik secim: PREFERENCE sirasina gore ilk bulunan."""
    devs = available_devices()
    for kind in PREFERENCE:
        for d in devs:
            if d.kind == kind:
                return d
    return devs[-1]  # cpu -- buraya asla dusmemeli ama sigorta


# ------------------------------------------------------------------ dogrulama
def _parse(spec: str) -> DeviceInfo:
    """
    "cuda" / "xpu:1" / "cpu" -> DeviceInfo.

    ISTENEN CIHAZ YOKSA HATA VERIR, sessizce CPU'ya DUSMEZ.
    Sessizce dusmek, kullanicinin GPU'da egittigini sanip saatlerce CPU'da
    beklemesi demektir. Yanlis cihaz gurultulu sekilde patlamali.
    """
    spec = spec.strip().lower()
    if ":" in spec:
        kind, _, idx = spec.partition(":")
        index = int(idx)
    else:
        kind, index = spec, 0

    if kind == "auto":
        return best_device()

    devs = [d for d in available_devices() if d.kind == kind]
    if not devs:
        have = sorted({d.kind for d in available_devices()})
        raise ValueError(
            f"'{spec}' bu makinede yok. Kullanilabilir: {have}. "
            f"Otomatik secim icin 'auto' kullan."
        )

    match = [d for d in devs if d.index == index]
    if not match:
        raise ValueError(
            f"'{spec}' yok -- {kind} icin gecerli indeksler: "
            f"{[d.index for d in devs]}"
        )
    return match[0]


# ----------------------------------------------------------------- interaktif
def _is_interactive() -> bool:
    """
    Gercek bir terminalde miyiz?

    Notebook, pytest, cron, FastAPI: HAYIR. Bu durumlarda soru sorulmaz.
    stdin yoksa/kapaliysa input() ya EOFError atar ya da asili kalir --
    ikisi de kabul edilemez.
    """
    if os.environ.get("SPP_NO_PROMPT"):
        return False
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:  # noqa: BLE001
        return False


def ask_device(devices: list[DeviceInfo] | None = None) -> DeviceInfo:
    """
    Kullaniciya sorar. SADECE gercek terminalde cagrilmali.
    Bos girdi / EOF / Ctrl-C -> otomatik secim (akisi bloke etmez).
    """
    devs = devices or available_devices()
    default = best_device()

    print("\nKullanilabilir cihazlar:")
    for i, d in enumerate(devs, 1):
        mark = " (onerilen)" if d.spec == default.spec else ""
        print(f"  {i}) {d}{mark}")

    try:
        raw = input(f"\nCihaz secin [1-{len(devs)}] (bos = {default.spec}): ").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n-> otomatik: {default.spec}")
        return default

    if not raw:
        return default

    try:
        i = int(raw)
        if 1 <= i <= len(devs):
            return devs[i - 1]
    except ValueError:
        # Sayi yerine "cuda" / "cpu" yazmis olabilir -- kabul et.
        try:
            return _parse(raw)
        except ValueError as e:
            print(f"  ! {e}")

    print(f"  ! gecersiz secim, otomatige donuluyor: {default.spec}")
    return default


# -------------------------------------------------------------------- secim
def select_device(
    prefer: str | None = None,
    *,
    ask: bool = False,
    remember: bool = True,
) -> torch.device:
    """
    Cihazi coozer. Modulun ana giris noktasi.

    Args:
        prefer:   "cuda" / "xpu:1" / "cpu" / "auto" / None
        ask:      True ise VE gercek terminal varsa kullaniciya sorar.
                  Notebook/test/sunucuda bu bayrak sessizce yok sayilir.
        remember: secimi surec boyunca hatirla (ikinci kez sorma)

    Doner: torch.device
    """
    global _selected

    # 1) acik deger
    if prefer:
        d = _parse(prefer).torch_device
        if remember:
            _selected = d
        return d

    # 2) ortam degiskeni -- CI/script icin en pratik yol
    env = os.environ.get(ENV_VAR)
    if env:
        d = _parse(env).torch_device
        log.info("%s=%s -> %s", ENV_VAR, env, d)
        if remember:
            _selected = d
        return d

    # 3) bu surecte zaten secilmis
    if _selected is not None:
        return _selected

    # 4) sor (sadece gercek terminalde)
    if ask and _is_interactive():
        d = ask_device().torch_device
        if remember:
            _selected = d
        return d

    # 5) otomatik
    d = best_device().torch_device
    if remember:
        _selected = d
    return d


def set_device(spec: str) -> torch.device:
    """Secimi elle sabitle (notebook'ta pratik: set_device('cpu'))."""
    global _selected
    _selected = _parse(spec).torch_device
    return _selected


def reset_device() -> None:
    """Hatirlanan secimi unut -- bir sonraki select_device tekrar coozer."""
    global _selected
    _selected = None


def current_device() -> torch.device | None:
    """Su an hatirlanan secim (henuz secilmediyse None)."""
    return _selected


# ---------------------------------------------------------------- bellek/temiz
def free_cache(device: torch.device | None = None) -> None:
    """
    Hizlandirici bellegini birak. Cihaz turune gore dogru cagriyi yapar.

    NEDEN VAR: ard arda onlarca model egitilirken (ozellik supurmesi, coklu
    ticker) XPU'nun caching allocator'i bellegi geri vermiyor ve bir yerde
    UR_RESULT_ERROR_OUT_OF_RESOURCES ile cokuyor (torch 2.13.0+xpu).
    CUDA'da ayni risk daha az ama cagri zararsiz.
    """
    d = device or _selected or best_device().torch_device
    kind = d.type if isinstance(d, torch.device) else str(d)

    if kind == "cuda" and torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif kind == "xpu" and hasattr(torch, "xpu") and torch.xpu.is_available():
        torch.xpu.empty_cache()
    # mps/cpu: yapacak bir sey yok


def seed_device(seed: int) -> None:
    """Cihaza ozel RNG tohumu. Bulunmayan backend sessizce atlanir."""
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        torch.xpu.manual_seed_all(seed)


# --------------------------------------------------------------------- rapor
def describe() -> str:
    devs = available_devices()
    lines = [f"torch {torch.__version__}", "", "Kullanilabilir cihazlar:"]
    best = best_device()
    for d in devs:
        mark = "  <- otomatik secim" if d.spec == best.spec else ""
        lines.append(f"  {d}{mark}")

    env = os.environ.get(ENV_VAR)
    lines.append("")
    lines.append(f"{ENV_VAR} = {env or '(ayarlanmamis)'}")
    lines.append(f"hatirlanan secim = {_selected or '(henuz yok)'}")
    lines.append(f"interaktif terminal = {_is_interactive()}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
    if _is_interactive():
        d = ask_device()
        print(f"\nSecilen: {d.torch_device}")
    else:
        print("\n(terminal yok -- soru sorulmadi, otomatik secim gecerli)")
