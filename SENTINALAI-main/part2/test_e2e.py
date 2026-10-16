import asyncio
import json
import urllib.request
import websockets

async def test_full_pipeline():
    uri = 'ws://localhost:8000/ws/incidents'
    async with websockets.connect(uri) as ws:
        # 1. Trigger simulate via REST POST
        req = urllib.request.Request(
            'http://localhost:8000/api/simulate',
            data=json.dumps({'type': 'fall_collapse', 'camera_id': 'cam_01'}).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req)
        simulated = json.loads(resp.read().decode())
        print('Simulate API response:', simulated['id'], simulated['type'], simulated['severity'])

        # 2. Read created event from WebSocket (filter for simulated incident amidst live camera streams)
        created_found = False
        for _ in range(20):
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            if data.get('event') == 'incident.created' and data.get('data', {}).get('id') == simulated['id']:
                print('WebSocket received event:', data['event'], data['data']['id'])
                created_found = True
                break
        assert created_found, f"Simulated incident {simulated['id']} not received on WebSocket"

        # 3. Patch incident to acknowledged
        patch_req = urllib.request.Request(
            f"http://localhost:8000/api/incidents/{simulated['id']}",
            data=json.dumps({'status': 'acknowledged', 'notes': 'Test Ack'}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='PATCH'
        )
        patch_resp = urllib.request.urlopen(patch_req)
        patched = json.loads(patch_resp.read().decode())
        print('Patch API response:', patched['status'], patched['notes'])

        # 4. Read update event from WebSocket (filter for patched incident)
        updated_found = False
        for _ in range(20):
            update_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            update_data = json.loads(update_msg)
            if update_data.get('event') == 'incident.updated' and update_data.get('data', {}).get('id') == simulated['id']:
                print('WebSocket received update event:', update_data['event'], update_data['data']['status'])
                assert update_data['data']['status'] == 'acknowledged'
                updated_found = True
                break
        assert updated_found, f"Update event for {simulated['id']} not received on WebSocket"

        print('ALL END-TO-END FLOWS VERIFIED 100% SUCCESSFULLY!')

if __name__ == '__main__':
    asyncio.run(test_full_pipeline())
