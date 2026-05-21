# AgenticStack Test Dashboard

Professional testing interface for AgenticStack API with real-time debugging.

## Features

✅ **Three-panel layout:**
- **Left**: App configuration, tools registry, state setup
- **Center**: Chat interface for real-time testing
- **Right**: Debug info - turn ID, state, tool calls, raw responses

✅ **Complete visibility:**
- All tools with their input/output schemas
- Current application state (JSON)
- Turn ID tracking
- Message history with counts
- Tool call visualization
- Raw API responses

✅ **Professional UI:**
- Clean, production-ready design
- Blue/gray color scheme (not purple)
- Responsive layout
- JSON syntax highlighting
- Real-time updates

## Usage

### Start Backend
```bash
docker-compose -f docker-compose.local.yml up
```

### Start Dashboard
```bash
cd test_web
python main.py
```

### Open Browser
```
http://localhost:8888
```

## Layout

```
┌─────────────┬─────────────────────┬──────────────┐
│             │                     │              │
│  Left       │    Main Chat        │   Right      │
│  Sidebar    │    Interface        │   Sidebar    │
│             │                     │              │
│  • App      │  • Messages         │  • State     │
│    Config   │  • Input            │  • Turn ID   │
│  • Tools    │  • Tool Calls       │  • Stats     │
│    List     │                     │  • Response  │
│  • State    │                     │              │
│             │                     │              │
└─────────────┴─────────────────────┴──────────────┘
```

## How to Test

1. **Configure App**
   - Enter app name, description, user ID
   - Customize default state (JSON)
   - Click "Register App"

2. **View Available Tools**
   - Left sidebar shows all registered tools
   - See tool names, parameters, input/output types

3. **Chat**
   - Type message in chat input
   - See instant response in messages

4. **Monitor Tools**
   - If tools are called, see them in messages
   - Right sidebar shows active tool calls
   - View turn ID and state changes

5. **Execute & Continue**
   - Click "Execute & Continue" for tool calls
   - See mock tool results
   - Watch final agent response

6. **Debug**
   - Right sidebar shows all debug info
   - View current state (JSON)
   - See turn ID, message count, tool call count
   - Raw API response available

## File Structure

```
test_web/
├── main.py          # FastAPI backend (serves UI, proxies API)
├── index.html       # Main dashboard HTML
├── styles.css       # Professional styling
├── app.js           # Frontend logic
└── README.md        # This file
```

## API Endpoints

The test dashboard proxies to your backend:

- `POST /api/register` → `POST /v1/apps`
- `POST /api/chat` → `POST /v1/chat`
- `POST /api/tools` → `POST /v1/chat/tools`

## Configuration

Edit `index.html` to change:
- Default app name
- Default user ID
- Default state JSON
- App description

Edit `main.py` to change:
- Backend URL (default: `http://localhost:8848`)
- Dashboard port (default: `8888`)

## Troubleshooting

### Dashboard won't start
```bash
# Kill process on port 8888
lsof -ti :8888 | xargs kill -9

# Restart
python main.py
```

### Backend connection fails
```bash
# Check backend is running
curl http://localhost:8848/v1/health

# If not, start it:
docker-compose -f docker-compose.local.yml up
```

### Tools not showing
```bash
# Register app first
# Then check right sidebar for debug info
# See raw response for registration details
```

## Features in Detail

### Left Sidebar
- **App Configuration**: Register and configure your app
- **Default State**: JSON object sent on registration
- **Tools List**: All available tools with schemas (shows when registered)

### Center Panel
- **Chat Messages**: User messages in blue, agent replies in gray
- **Tool Calls**: Displayed in purple, showing tool name and input
- **Message Input**: Type and send messages (only active after registration)
- **Execute Button**: Appears when tools are called

### Right Sidebar
- **Current State**: JSON representation of app state
- **Turn Information**: Current turn ID, app ID, user ID
- **Active Tool Calls**: Tools currently being executed with inputs
- **Conversation Stats**: Message count, tool call count, status
- **Raw Response**: Full JSON response from last API call

## Tips for Testing

1. **Test Tool Triggering**
   - Ask something that should trigger a tool: "find a property"
   - Watch for tool call in center panel
   - See tool details in right sidebar

2. **Test State Updates**
   - Make calls, watch state change in right sidebar
   - Verify state is JSON in debug panel

3. **Test Tool Execution**
   - Click "Execute & Continue" after tool call
   - Mock results are shown
   - See final agent response

4. **Monitor Conversation**
   - Track message count in stats
   - Watch turn ID change for each turn
   - See conversation status change

5. **Debug Issues**
   - Check raw response for error details
   - Verify turn ID matches expectations
   - Confirm state structure is correct

## Production Use

This dashboard is for **local development testing only**. For production:

1. Use the API directly via HTTP
2. Implement authentication (add API key)
3. Deploy dashboard separately if needed
4. Use Swagger UI at `/docs` endpoint

## Related Files

- `LOCAL_DEVELOPMENT.md` - Full setup guide
- `API_TESTING.md` - API integration patterns
- `REAL_ESTATE_TESTING.md` - Domain scenario details
- `docker-compose.yml` - Production setup
- `docker-compose.local.yml` - Local dev setup

---

Happy testing! 🚀
