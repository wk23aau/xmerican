/**
 * CDP REPL - Interactive Chrome DevTools Protocol Browser Automation
 * 
 * Connects to Chrome's remote debugging port and provides an interactive
 * REPL session for browser automation.
 * 
 * Usage: node cdp-repl.js
 * 
 * Interactive Commands:
 *   tabs                     - List all open tabs
 *   new [url]                - Open new tab (optional URL)
 *   switch <tabId>           - Switch to tab by ID
 *   close [tabId]            - Close tab (current if no ID)
 *   goto <url>               - Navigate current tab to URL
 *   screenshot               - Take screenshot (always saves to capture.png)
 *   click <x> <y>            - Click at coordinates
 *   type <text>              - Type text
 *   press <key>              - Press key (Enter, Tab, Escape, etc.)
 *   scroll <x> <y>           - Scroll by x,y pixels
 *   hover <x> <y>            - Move mouse to coordinates
 *   eval <javascript>        - Evaluate JavaScript in page
 *   wait <ms>                - Wait for milliseconds
 *   viewport                 - Get current viewport size
 *   help                     - Show available commands
 *   exit                     - Exit REPL
 */

const http = require('http');
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const CDP_PORT = process.env.CDP_PORT || 9222;
const CDP_HOST = process.env.CDP_HOST || 'localhost';

// Current active tab
let activeTabId = null;
let ws = null;
let messageId = 0;
let pendingMessages = new Map();

/**
 * Fetch JSON from CDP HTTP endpoint
 */
function fetchJSON(urlPath) {
    return new Promise((resolve, reject) => {
        const url = `http://${CDP_HOST}:${CDP_PORT}${urlPath}`;
        http.get(url, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    resolve(JSON.parse(data));
                } catch (e) {
                    reject(new Error(`Failed to parse JSON: ${data}`));
                }
            });
        }).on('error', reject);
    });
}

/**
 * Get list of all tabs/targets
 */
async function getTabs() {
    const targets = await fetchJSON('/json');
    return targets.filter(t => t.type === 'page');
}

/**
 * Connect to a specific tab via WebSocket
 */
async function connectToTab(tabId) {
    const targets = await fetchJSON('/json');
    const target = targets.find(t => t.id === tabId);

    if (!target) {
        throw new Error(`Tab ${tabId} not found`);
    }

    if (!target.webSocketDebuggerUrl) {
        throw new Error(`Tab ${tabId} has no WebSocket URL (may be attached elsewhere)`);
    }

    return new Promise((resolve, reject) => {
        if (ws) {
            ws.close();
        }

        ws = new WebSocket(target.webSocketDebuggerUrl);

        ws.on('open', () => {
            activeTabId = tabId;
            resolve();
        });

        ws.on('message', (data) => {
            const msg = JSON.parse(data.toString());
            if (msg.id && pendingMessages.has(msg.id)) {
                const { resolve, reject } = pendingMessages.get(msg.id);
                pendingMessages.delete(msg.id);
                if (msg.error) {
                    reject(new Error(msg.error.message));
                } else {
                    resolve(msg.result);
                }
            }
        });

        ws.on('error', reject);
        ws.on('close', () => {
            if (activeTabId === tabId) {
                activeTabId = null;
            }
        });
    });
}

/**
 * Send CDP command and wait for response
 */
function sendCommand(method, params = {}) {
    return new Promise((resolve, reject) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            reject(new Error('Not connected to any tab. Use "tabs" then "switch <id>"'));
            return;
        }

        const id = ++messageId;
        pendingMessages.set(id, { resolve, reject });

        ws.send(JSON.stringify({ id, method, params }));

        // Timeout after 30 seconds
        setTimeout(() => {
            if (pendingMessages.has(id)) {
                pendingMessages.delete(id);
                reject(new Error(`Command ${method} timed out`));
            }
        }, 30000);
    });
}

/**
 * Auto-connect to first available tab
 */
async function autoConnect() {
    if (ws && ws.readyState === WebSocket.OPEN) return true;

    const tabs = await getTabs();
    if (tabs.length > 0) {
        await connectToTab(tabs[0].id);
        await sendCommand('Page.enable');
        await sendCommand('Runtime.enable');
        await sendCommand('Input.enable');
        return true;
    }
    return false;
}

// ============ CDP COMMANDS ============

async function listTabs() {
    const tabs = await getTabs();
    console.log('\n📑 Open Tabs:');
    tabs.forEach((t, i) => {
        const active = t.id === activeTabId ? ' ← ACTIVE' : '';
        console.log(`  [${i}] ${t.id}`);
        console.log(`      Title: ${t.title}`);
        console.log(`      URL: ${t.url}${active}`);
    });
    return tabs;
}

async function newTab(url = 'about:blank') {
    const result = await fetchJSON(`/json/new?${encodeURIComponent(url)}`);
    console.log(`✅ New tab: ${result.id}`);
    return result;
}

async function closeTab(tabId) {
    const id = tabId || activeTabId;
    if (!id) throw new Error('No tab specified and no active tab');
    await fetchJSON(`/json/close/${id}`);
    if (id === activeTabId) {
        activeTabId = null;
        if (ws) ws.close();
    }
    console.log(`✅ Closed tab: ${id}`);
}

async function switchTab(tabId) {
    // Allow switching by index
    if (/^\d+$/.test(tabId)) {
        const tabs = await getTabs();
        const idx = parseInt(tabId);
        if (idx >= 0 && idx < tabs.length) {
            tabId = tabs[idx].id;
        }
    }

    await connectToTab(tabId);
    await sendCommand('Page.enable');
    await sendCommand('Runtime.enable');
    await sendCommand('Input.enable');
    console.log(`✅ Switched to tab: ${tabId}`);
}

async function navigate(url) {
    await autoConnect();
    if (!url.startsWith('http')) url = 'https://' + url;
    await sendCommand('Page.navigate', { url });
    console.log(`✅ Navigating to: ${url}`);
}

async function screenshot() {
    await autoConnect();

    const result = await sendCommand('Page.captureScreenshot', {
        format: 'png',
        quality: 100,
        fromSurface: true,
        captureBeyondViewport: false
    });

    const buffer = Buffer.from(result.data, 'base64');
    const filepath = path.resolve('capture.png');
    fs.writeFileSync(filepath, buffer);
    console.log(`✅ Screenshot saved: capture.png (${buffer.length} bytes)`);
}

async function click(x, y) {
    await autoConnect();
    x = parseInt(x);
    y = parseInt(y);

    await sendCommand('Input.dispatchMouseEvent', {
        type: 'mousePressed', x, y, button: 'left', clickCount: 1
    });
    await sendCommand('Input.dispatchMouseEvent', {
        type: 'mouseReleased', x, y, button: 'left', clickCount: 1
    });
    console.log(`✅ Clicked: (${x}, ${y})`);
}

async function hover(x, y) {
    await autoConnect();
    x = parseInt(x);
    y = parseInt(y);
    await sendCommand('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
    console.log(`✅ Hover: (${x}, ${y})`);
}

async function typeText(text) {
    await autoConnect();
    for (const char of text) {
        await sendCommand('Input.dispatchKeyEvent', { type: 'keyDown', text: char });
        await sendCommand('Input.dispatchKeyEvent', { type: 'keyUp', text: char });
    }
    console.log(`✅ Typed: "${text}"`);
}

async function pressKey(key) {
    await autoConnect();
    const keyMap = {
        'Enter': { key: 'Enter', code: 'Enter', keyCode: 13 },
        'Tab': { key: 'Tab', code: 'Tab', keyCode: 9 },
        'Escape': { key: 'Escape', code: 'Escape', keyCode: 27 },
        'Backspace': { key: 'Backspace', code: 'Backspace', keyCode: 8 },
        'Delete': { key: 'Delete', code: 'Delete', keyCode: 46 },
        'ArrowUp': { key: 'ArrowUp', code: 'ArrowUp', keyCode: 38 },
        'ArrowDown': { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40 },
        'ArrowLeft': { key: 'ArrowLeft', code: 'ArrowLeft', keyCode: 37 },
        'ArrowRight': { key: 'ArrowRight', code: 'ArrowRight', keyCode: 39 },
        'Space': { key: ' ', code: 'Space', keyCode: 32 }
    };

    const keyInfo = keyMap[key] || { key, code: key, keyCode: 0 };
    await sendCommand('Input.dispatchKeyEvent', {
        type: 'keyDown', key: keyInfo.key, code: keyInfo.code, windowsVirtualKeyCode: keyInfo.keyCode
    });
    await sendCommand('Input.dispatchKeyEvent', {
        type: 'keyUp', key: keyInfo.key, code: keyInfo.code, windowsVirtualKeyCode: keyInfo.keyCode
    });
    console.log(`✅ Pressed: ${key}`);
}

async function scroll(x, y) {
    await autoConnect();
    x = parseInt(x);
    y = parseInt(y);
    await sendCommand('Input.dispatchMouseEvent', {
        type: 'mouseWheel', x: 200, y: 200, deltaX: x, deltaY: y
    });
    console.log(`✅ Scrolled: (${x}, ${y})`);
}

async function evalJS(expression) {
    await autoConnect();
    const result = await sendCommand('Runtime.evaluate', {
        expression, returnByValue: true
    });
    if (result.result) {
        console.log('📤 Result:', result.result.value);
    }
    if (result.exceptionDetails) {
        console.log('❌ Error:', result.exceptionDetails.text);
    }
}

async function wait(ms) {
    await new Promise(resolve => setTimeout(resolve, parseInt(ms)));
    console.log(`✅ Waited: ${ms}ms`);
}

async function getViewport() {
    await autoConnect();
    const result = await sendCommand('Runtime.evaluate', {
        expression: 'JSON.stringify({ width: window.innerWidth, height: window.innerHeight })',
        returnByValue: true
    });
    const vp = JSON.parse(result.result.value);
    console.log(`📐 Viewport: ${vp.width}×${vp.height}`);
}

/**
 * Get World State - Scans page for interactive elements (Action Map)
 * Based on world.md concepts: geometry-first, semantics-second
 */
async function getWorldState() {
    await autoConnect();

    // JavaScript to inject into the page to scan for interactive elements
    const scanScript = `
        (function() {
            const viewport = { width: window.innerWidth, height: window.innerHeight };
            const elements = [];
            let idCounter = 0;
            
            // Interactive element selectors
            const selectors = [
                'button',
                'a[href]',
                'input',
                'select',
                'textarea',
                '[role="button"]',
                '[role="link"]',
                '[role="menuitem"]',
                '[role="tab"]',
                '[role="checkbox"]',
                '[role="radio"]',
                '[onclick]',
                '[tabindex]:not([tabindex="-1"])',
                'label[for]'
            ];
            
            const candidates = document.querySelectorAll(selectors.join(','));
            
            candidates.forEach((el) => {
                const rect = el.getBoundingClientRect();
                
                // Skip invisible or off-screen elements
                if (rect.width === 0 || rect.height === 0) return;
                if (rect.bottom < 0 || rect.top > viewport.height) return;
                if (rect.right < 0 || rect.left > viewport.width) return;
                
                // Check visibility
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
                
                // Get label (try multiple sources)
                const label = 
                    el.getAttribute('aria-label') ||
                    el.getAttribute('title') ||
                    el.getAttribute('placeholder') ||
                    el.innerText?.trim().substring(0, 50) ||
                    el.getAttribute('name') ||
                    el.getAttribute('id') ||
                    '';
                
                // Get role
                const role = 
                    el.getAttribute('role') ||
                    el.tagName.toLowerCase();
                
                // Get element type
                const type = el.getAttribute('type') || role;
                
                // Calculate center point (for clicking)
                const centerX = Math.round(rect.left + rect.width / 2);
                const centerY = Math.round(rect.top + rect.height / 2);
                
                // Check occlusion (is something blocking this element?)
                const elAtCenter = document.elementFromPoint(centerX, centerY);
                const isOccluded = elAtCenter && !el.contains(elAtCenter) && !elAtCenter.contains(el) && elAtCenter !== el;
                
                // Get state
                const state = {
                    disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
                    checked: el.checked || el.getAttribute('aria-checked') === 'true',
                    expanded: el.getAttribute('aria-expanded') === 'true',
                    selected: el.getAttribute('aria-selected') === 'true'
                };
                
                // Generate stable ID
                const id = 'el_' + idCounter++;
                
                elements.push({
                    id,
                    label: label.substring(0, 60),
                    role,
                    type,
                    rect: {
                        x: Math.round(rect.left),
                        y: Math.round(rect.top),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    },
                    center: { x: centerX, y: centerY },
                    state,
                    occluded: isOccluded,
                    tag: el.tagName.toLowerCase()
                });
            });
            
            return JSON.stringify({
                timestamp: new Date().toISOString(),
                viewport,
                cursor: { x: 0, y: 0 },
                elementCount: elements.length,
                elements
            }, null, 2);
        })()
    `;

    const result = await sendCommand('Runtime.evaluate', {
        expression: scanScript,
        returnByValue: true
    });

    if (result.result && result.result.value) {
        const worldState = JSON.parse(result.result.value);

        // Save to output/world.json
        const outputDir = path.resolve('output');
        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
        }
        const filepath = path.join(outputDir, 'world.json');
        fs.writeFileSync(filepath, result.result.value);

        console.log(`\n🌍 World State captured:`);
        console.log(`   Viewport: ${worldState.viewport.width}×${worldState.viewport.height}`);
        console.log(`   Elements: ${worldState.elementCount} interactive candidates`);
        console.log(`   Saved to: output/world.json`);
        console.log(`\n   Top 5 elements:`);
        worldState.elements.slice(0, 5).forEach((el, i) => {
            console.log(`   ${i + 1}. [${el.id}] ${el.role}: "${el.label}" @ (${el.center.x}, ${el.center.y})${el.occluded ? ' [OCCLUDED]' : ''}`);
        });
    } else if (result.exceptionDetails) {
        console.log('❌ Error scanning world:', result.exceptionDetails.text);
    }
}

function showHelp() {
    console.log(`
╔════════════════════════════════════════════════════════════════╗
║                    CDP REPL Commands                           ║
╠════════════════════════════════════════════════════════════════╣
║ TABS                                                           ║
║   tabs              List all open tabs                         ║
║   new [url]         Open new tab                               ║
║   switch <id|idx>   Switch to tab (by ID or index)             ║
║   close [id]        Close tab                                  ║
╠════════════════════════════════════════════════════════════════╣
║ NAVIGATION                                                     ║
║   goto <url>        Navigate to URL                            ║
║   screenshot        Save to capture.png (replaces previous)    ║
║   viewport          Show viewport dimensions                   ║
╠════════════════════════════════════════════════════════════════╣
║ INPUT                                                          ║
║   click <x> <y>     Click at coordinates                       ║
║   hover <x> <y>     Move mouse to coordinates                  ║
║   type <text>       Type text                                  ║
║   press <key>       Press key (Enter, Tab, Escape, etc.)       ║
║   scroll <x> <y>    Scroll by pixels                           ║
╠════════════════════════════════════════════════════════════════╣
║ PERCEPTION                                                     ║
║   world             Scan page for interactive elements         ║
║                     (Action Map → output/world.json)           ║
╠════════════════════════════════════════════════════════════════╣
║ OTHER                                                          ║
║   eval <js>         Execute JavaScript                         ║
║   wait <ms>         Wait milliseconds                          ║
║   help              Show this help                             ║
║   exit              Exit REPL                                  ║
╚════════════════════════════════════════════════════════════════╝
`);
}

// ============ INTERACTIVE REPL ============

async function processCommand(input) {
    const parts = input.trim().split(/\s+/);
    const cmd = parts[0]?.toLowerCase();
    const args = parts.slice(1);

    if (!cmd) return true;

    try {
        switch (cmd) {
            case 'tabs':
                await listTabs();
                break;
            case 'new':
                await newTab(args[0]);
                break;
            case 'switch':
                if (!args[0]) throw new Error('Tab ID or index required');
                await switchTab(args[0]);
                break;
            case 'close':
                await closeTab(args[0]);
                break;
            case 'goto':
            case 'navigate':
            case 'nav':
                if (!args[0]) throw new Error('URL required');
                await navigate(args[0]);
                break;
            case 'screenshot':
            case 'ss':
                await screenshot();
                break;
            case 'click':
                if (!args[0] || !args[1]) throw new Error('X and Y required');
                await click(args[0], args[1]);
                break;
            case 'hover':
                if (!args[0] || !args[1]) throw new Error('X and Y required');
                await hover(args[0], args[1]);
                break;
            case 'type':
                if (!args.length) throw new Error('Text required');
                await typeText(args.join(' '));
                break;
            case 'press':
                if (!args[0]) throw new Error('Key required');
                await pressKey(args[0]);
                break;
            case 'scroll':
                if (!args[0] || !args[1]) throw new Error('X and Y required');
                await scroll(args[0], args[1]);
                break;
            case 'eval':
                if (!args.length) throw new Error('JavaScript required');
                await evalJS(args.join(' '));
                break;
            case 'wait':
                if (!args[0]) throw new Error('Milliseconds required');
                await wait(args[0]);
                break;
            case 'viewport':
            case 'vp':
                await getViewport();
                break;
            case 'world':
            case 'w':
                await getWorldState();
                break;
            case 'help':
            case '?':
                showHelp();
                break;
            case 'exit':
            case 'quit':
            case 'q':
                return false;
            default:
                console.log(`❓ Unknown command: ${cmd}. Type "help" for commands.`);
        }
    } catch (error) {
        console.log(`❌ Error: ${error.message}`);
    }

    return true;
}

async function startREPL() {
    console.log(`
╔════════════════════════════════════════════════════════════════╗
║           CDP REPL - Interactive Browser Automation            ║
║                   Connecting to port ${CDP_PORT}...                     ║
╚════════════════════════════════════════════════════════════════╝
`);

    // Try to connect to first tab
    try {
        const connected = await autoConnect();
        if (connected) {
            console.log(`✅ Connected to active tab: ${activeTabId}\n`);
        } else {
            console.log('⚠️  No tabs found. Use "new" to create one.\n');
        }
    } catch (e) {
        console.log(`⚠️  Could not auto-connect: ${e.message}`);
        console.log('   Make sure Chrome is running with --remote-debugging-port=9222\n');
    }

    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    const prompt = () => {
        const tabInfo = activeTabId ? `[${activeTabId.substring(0, 8)}...]` : '[no tab]';
        rl.question(`cdp ${tabInfo}> `, async (input) => {
            const shouldContinue = await processCommand(input);
            if (shouldContinue) {
                prompt();
            } else {
                console.log('👋 Goodbye!');
                if (ws) ws.close();
                rl.close();
                process.exit(0);
            }
        });
    };

    showHelp();
    prompt();
}

// ============ MAIN ============

// If run with arguments, execute single command (for scripting)
if (process.argv.length > 2) {
    const args = process.argv.slice(2);
    processCommand(args.join(' ')).then(() => {
        if (ws) ws.close();
        process.exit(0);
    }).catch(e => {
        console.error(`❌ Error: ${e.message}`);
        process.exit(1);
    });
} else {
    // Start interactive REPL
    startREPL();
}
