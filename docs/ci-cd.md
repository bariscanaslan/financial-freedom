# Jenkins CI/CD

Bu yapi GitHub pull request'lerinde test ve production image build'i yapar.
Yalnizca `main` dalindaki basarili build canli ortami gunceller. Testler host
portu acmadigi icin canli `3007`, `8089` ve `6389` portlariyla cakisma olmaz.

## Pipeline davranisi

| Olay | Test | Image build | Canli deploy |
|---|---:|---:|---:|
| Pull request | Evet | Evet | Hayir |
| `main` push/merge | Evet | Evet | Evet |
| Diger dal push | Evet | Evet | Hayir |

Backend testleri `unit`, `integration` ve `regression` katmanlarinda pytest ile
kosar. Frontend testleri Vitest ile kosar. JUnit ve coverage dosyalari Jenkins
artifact'i olarak saklanir. Eski `tests/smoke_*.py` ve `tests/run_*.py`
deneyleri gecelik/manual islere ayrilmak uzere korunmustur; canli deploy'u
yfinance veya uzun model egitimine baglamaz.

## Sunucu on kosullari

Jenkins agent container'inda sunlar bulunmalidir:

- `docker` CLI
- Docker Compose v2 (`docker compose`)
- `git`, POSIX `sh` ve `install`
- Host Docker socket'i: `/var/run/docker.sock`
- Canli dizin ayni mutlak yolda: `/srv/financial-freedom`

Ornek Jenkins mount'lari:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - /srv/financial-freedom:/srv/financial-freedom
```

Jenkins agent label'i `docker` olmalidir. Farkli bir label kullaniliyorsa
`Jenkinsfile` icindeki `agent` degeri degistirilmelidir.

> Docker socket erisimi host uzerinde root seviyesine yakin yetki verir.
> Jenkins'i yalnizca VPN/yonetim aginda tutun ve guvenilmeyen repolara job
> tanimlamayin.

## Canli dizini hazirlama

Mevcut canli kurulumun dizini `/srv/financial-freedom` olarak kullanilmalidir.
Farkli bir dizindeyse ya bu dizine tasiyin ya da `Jenkinsfile` icindeki
`DEPLOY_DIR` degerini degistirip Jenkins container'ina ayni mutlak yolda mount
edin.

Canli `.env` repoya alinmaz. Jenkins'te `financial-freedom-production-env`
kimlikli bir **Secret file** credential olarak saklanir. Pipeline gecici secret
dosyasini okur ve deploy sirasinda canli dizine `0600` izniyle yazar:

```dotenv
DEPLOY_DIR=/srv/financial-freedom
DEPLOY_PROJECT_NAME=financial-freedom
VPN_BIND_ADDRESS=10.8.0.1
FRONTEND_PORT=3007
BACKEND_PORT=8089
REDIS_PORT=6389
```

Asagidaki dizinler kalicidir ve pipeline tarafindan silinmez:

```text
/srv/financial-freedom/cache
/srv/financial-freedom/models
/srv/financial-freedom/portfolio_data
```

Ilk otomatik deploy'dan once mevcut SQLite ve modellerin yedegini alin.

## Mevcut Compose proje adini dogrulama

Pipeline `financial-freedom` Compose proje adini kullanir. Mevcut container'in
etiketini kontrol edin:

```bash
docker inspect <mevcut-api-container> \
  --format '{{ index .Config.Labels "com.docker.compose.project" }}'
```

Sonuc farkliysa `Jenkinsfile` icindeki `DEPLOY_PROJECT_NAME` degerini mevcut
adla ayni yapin. Aksi halde yeni proje ayni portlari almaya calisir.

## GitHub ve Jenkins

Onerilen kurulum Jenkins Multibranch Pipeline + GitHub Branch Source'tur:

1. Jenkins'te GitHub Branch Source eklentisini kurun.
2. Yeni bir Multibranch Pipeline olusturup repository URL/credential girin.
3. PR discovery ve branch discovery davranislarini etkinlestirin.
4. GitHub repository webhook'unu Jenkins GitHub endpoint'ine yonlendirin.
5. Jenkinsfile'in repository kokunden bulunabildigini dogrulayin.
6. Branch protection'da Jenkins test sonucunu zorunlu status check yapin.

GitHub'da PR acilmasi/guncellenmesi testleri baslatir. PR build'i deploy olmaz.
PR `main` dalina merge edildiginde webhook yeni `main` build'ini baslatir ve
testlerden sonra deploy gerceklesir.

## Deploy ve rollback

Image'lar commit SHA ile etiketlenir. Deploy asamasi:

1. Mevcut API/UI image kimliklerini kaydeder.
2. Test edilmis SHA image'lariyla `docker compose up -d --no-build --wait`
   calistirir.
3. Container health check'lerini bekler.
4. Nginx uzerinden `/api/health` yolunu kontrol eder.
5. Kontrol basarisizsa onceki API/UI image kimliklerini geri yukler.

Redis, SQLite, model ve cache verileri yeniden olusturulmaz. Compose servis
isimleri ve proje adi sabit kaldigi icin mevcut kalici dizinler korunur.

## Yerel komutlar

Docker daemon calisirken Jenkins ile ayni kalite kapisini kosmak icin:

```bash
export API_IMAGE=financial-freedom-api:local
export UI_IMAGE=financial-freedom-ui:local
scripts/ci/test.sh
```

Canli deploy komutu yalnizca sunucuda ve dogru `DEPLOY_DIR` ile calistirilmalidir.
