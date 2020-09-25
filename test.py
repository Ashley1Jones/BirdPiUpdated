import datetime
import time
import os
os.mkdi

def timelapse(start, end, length, fps):
    difference = lambda x, y: (x - y).total_seconds()
    now = lambda: datetime.datetime.now()

    start = datetime.datetime.strptime(start, '%d/%m/%Y %H:%M')
    end = datetime.datetime.strptime(end, '%d/%m/%Y %H:%M')

    assert difference(end, now()) > 0 and difference(end, start) > 0

    if difference(start, now()) < 0:
        start = now()

    n_frames = int(length * fps)

    delta = difference(end, start)

    for i in range(n_frames):
        target = start + datetime.timedelta(seconds=(i / n_frames) * delta)
        while difference(now(), target) < 0:
            time.sleep(1)
            print(f"Waiting...  seconds to go:"
                  f" {difference(target, now())}")
        print("Take Snapshot")


timelapse("09/09/2020 12:03", "09/09/2020 12:50", 30, 12)
