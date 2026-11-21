import sys
sys.path.insert(0, r'C:\Users\HARIS\Desktop\SecureFed-IDS\web\backend')

from app.schemas import TrainingRequest

# Test that client_count=2 is accepted
req = TrainingRequest(client_count=2, rounds=1, local_epochs=1, batch_size=8, learning_rate=0.001)
d = req.model_dump()
print('TrainingRequest with client_count=2: OK - rounds=%s, client_count=%s' % (d['rounds'], d['client_count']))

req2 = TrainingRequest(client_count=3, rounds=1, local_epochs=1, batch_size=8, learning_rate=0.001)
d2 = req2.model_dump()
print('TrainingRequest with client_count=3: OK - rounds=%s, client_count=%s' % (d2['rounds'], d2['client_count']))

# Test that invalid count still fails
try:
    req3 = TrainingRequest(client_count=5, rounds=1, local_epochs=1, batch_size=8, learning_rate=0.001)
    print('ERROR: client_count=5 should have been rejected')
except ValueError as e:
    print('client_count=5 correctly rejected: %s' % e)