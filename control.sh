#!/bin/bash

# SigmaChanBot Control Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

case "$1" in
    start)
        echo -e "${YELLOW}Starting SigmaChanBot...${NC}"
        source venv/bin/activate
        nohup python bot.py > bot.log 2>&1 &
        sleep 1
        if pgrep -f "python bot" > /dev/null; then
            echo -e "${GREEN}✅ Bot started successfully${NC}"
            echo "Logs: tail -f bot.log"
        else
            echo -e "${RED}❌ Failed to start bot${NC}"
        fi
        ;;
    stop)
        echo -e "${YELLOW}Stopping SigmaChanBot...${NC}"
        pkill -f "python bot"
        sleep 1
        if ! pgrep -f "python bot" > /dev/null; then
            echo -e "${GREEN}✅ Bot stopped${NC}"
        else
            echo -e "${RED}❌ Failed to stop bot${NC}"
        fi
        ;;
    restart)
        $0 stop
        sleep 1
        $0 start
        ;;
    status)
        if pgrep -f "python bot" > /dev/null; then
            echo -e "${GREEN}✅ Bot is running${NC}"
            pgrep -f "python bot" -a
        else
            echo -e "${RED}❌ Bot is not running${NC}"
        fi
        ;;
    logs)
        tail -f bot.log
        ;;
    *)
        echo "SigmaChanBot Control Script"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the bot"
        echo "  stop    - Stop the bot"
        echo "  restart - Restart the bot"
        echo "  status  - Show bot status"
        echo "  logs    - Show live logs"
        ;;
esac
