# Zalo Bridge for nanobot

This bridge connects Zalo to nanobot's Python backend using [zca-js](https://github.com/trandinhthangdev/zca-js).

## Setup

### 1. Get Zalo Credentials

You need three pieces of information from your Zalo Web session:

1. **Cookie**: Login to [https://chat.zalo.me/](https://chat.zalo.me/) and extract cookies using:
   - [J2TEAM Cookies](https://chromewebstore.google.com/detail/j2team-cookies/okpidcojinmlaakglciglbpcpajaibco)
   - [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
   - [ZaloDataExtractor](https://github.com/JustKemForFun/ZaloDataExtractor)

2. **IMEI**: Open DevTools (F12) → Console, then run:

   ```javascript
   localStorage.getItem("z_uuid");
   // or
   localStorage.getItem("sh_z_uuid");
   ```

3. **User Agent**: In the same Console, run:

```javascript
navigator.userAgent;
```

### 2. Install Dependencies

```bash
cd bridge-zca
npm install
```

### 3. Build the Bridge

```bash
npm run build
```

### 4. Configure nanobot

Add to your `config.yaml`:

```yaml
channels:
  zalo:
    enabled: true
    bridge_url: "ws://localhost:3002"
    cookie: '[{"name":"...", "value":"...", ...}]' # Your cookie JSON
    imei: "your-imei-here"
    user_agent: "your-user-agent-here"
    allow_from:
      - "user_id_1"
      - "user_id_2"
```

### 5. Start the Bridge

```bash
npm start
```

The bridge will listen on `ws://localhost:3002` by default. You can change this:

```bash
BRIDGE_PORT=3003 npm start
```

### 6. Start nanobot

```bash
# In the main nanobot directory
python -m nanobot
```

## How It Works

1. The bridge creates a WebSocket server on port 3002
2. nanobot's Python backend connects to this WebSocket
3. On connection, nanobot sends login credentials
4. The bridge uses zca-js to connect to Zalo
5. Messages flow bidirectionally:
   - **Inbound**: Zalo → zca-js → WebSocket → Python
   - **Outbound**: Python → WebSocket → zca-js → Zalo

## Troubleshooting

### Login Failed

- Make sure your cookie is valid and not expired
- Try logging out and back in to Zalo Web to get fresh credentials
- Verify your IMEI and user agent match your browser session

### Connection Issues

- Check that the bridge is running: `npm start`
- Verify the port (3002) is not in use by another application
- Check firewall settings if running remotely

### Message Not Received

- Verify the sender's ID is in the `allow_from` list
- Check the bridge logs for errors
- Ensure the Zalo listener is started

## API Reference

See [zca-js documentation](https://zca-js.tdung.com/vi/) for more details on the Zalo API.
