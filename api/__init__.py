"""
API katmani: model/ ve portfolio/ katmanlarinin ince HTTP kabugu (FastAPI).

Bu katman yeni is mantigi URETMEZ; alt katmanlari cagirir ve sonucu JSON'a
cevirir. Hicbir endpoint aksiyon onerisi (al/sat) dondurmez; tahmin ciktilari
tanimlayicidir (dagilim + risk sinyali).

Calistirma:  uvicorn api.main:app
"""
