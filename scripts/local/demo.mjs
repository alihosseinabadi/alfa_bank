// Local, Docker-free demo runner for the Alfa-Kurs UI.
//
// It installs the frontend dependencies if they are missing, starts Vite in the
// explicitly labelled demo mode, waits until the page answers, and opens the
// default browser. It never calls the backend and needs no database: the cards
// it shows are fictional and are labelled as such in the UI.
//
// Usage:  node scripts/local/demo.mjs [--no-open] [--port 5173]

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import http from 'node:http'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as sleep } from 'node:timers/promises'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const frontend = join(root, 'frontend')
const windows = process.platform === 'win32'
const npm = windows ? 'npm.cmd' : 'npm'
const shell = windows

const args = process.argv.slice(2)
const noOpen = args.includes('--no-open')
const portFlag = args.indexOf('--port')
const port = Number(portFlag >= 0 ? args[portFlag + 1] : 5173) || 5173
const host = '127.0.0.1'
const url = `http://${host}:${port}`

function run(command, commandArgs, options) {
  // .cmd shims on Windows must go through cmd.exe; passing a single command line
  // avoids Node's shell-quoting deprecation warning.
  if (windows) {
    const line = [command, ...commandArgs].join(' ')
    return spawn(process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', line], { stdio: 'inherit', ...options })
  }
  return spawn(command, commandArgs, { stdio: 'inherit', ...options })
}

async function ping() {
  return await new Promise((done) => {
    const request = http.get(url, (response) => {
      response.resume()
      done(response.statusCode === 200)
    })
    request.on('error', () => done(false))
    request.setTimeout(1500, () => {
      request.destroy()
      done(false)
    })
  })
}

function openBrowser() {
  const child = windows
    ? spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' })
    : spawn(process.platform === 'darwin' ? 'open' : 'xdg-open', [url], { detached: true, stdio: 'ignore' })
  child.unref()
}

async function main() {
  if (!existsSync(join(frontend, 'node_modules', 'vite'))) {
    console.log('[demo] frontend dependencies are missing - running npm ci ...')
    const install = run(npm, ['ci'], { cwd: frontend })
    const code = await new Promise((done) => install.on('exit', done))
    if (code !== 0) {
      console.error('[demo] npm ci failed; fix the npm error above and retry')
      process.exit(code ?? 1)
    }
  }

  console.log(`[demo] starting the labelled demo UI on ${url}`)
  const server = run(
    npm,
    ['run', 'dev', '--', '--host', host, '--port', String(port), '--strictPort'],
    { cwd: frontend, env: { ...process.env, VITE_RECOMMENDATIONS_SOURCE: 'demo' } },
  )

  let announced = false
  for (let attempt = 0; attempt < 60 && !announced; attempt += 1) {
    if (await ping()) {
      announced = true
      console.log(`[demo] ready: ${url}`)
      console.log('[demo] demo cards are fictional; no database or Docker is used')
      if (!noOpen) openBrowser()
    } else {
      await sleep(500)
    }
  }
  if (!announced) console.warn(`[demo] the server did not answer in 30s; open ${url} manually`)

  server.on('exit', (code) => process.exit(code ?? 0))
  process.on('SIGINT', () => {
    server.kill()
    process.exit(0)
  })
}

main()
