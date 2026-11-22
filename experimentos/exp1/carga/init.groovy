// setUp: construye, a partir de la semilla, todo el calendario de llegadas y conflictos de la corrida.
import java.util.concurrent.*
import groovy.json.JsonOutput

long semilla   = (props.getProperty('semilla') ?: '1') as long
int  tasaMin   = (props.getProperty('tasa_min') ?: '400') as int
int  calentS   = (props.getProperty('calentamiento_s') ?: '60') as int
int  traficoS  = (props.getProperty('trafico_s') ?: '720') as int
int  colaS     = (props.getProperty('cola_s') ?: '60') as int        // margen para confirmaciones/revisiones finales
double pConf   = (props.getProperty('p_conflicto') ?: '0.05') as double
double pConfirma = (props.getProperty('p_confirma') ?: '0.70') as double
// Perfil de carga: 'constante' (EXP-1) o 'rampa' (EXP-2: calentamiento a tasa_min, rampa lineal a tasa_pico y pico sostenido).
String perfil  = props.getProperty('perfil') ?: 'constante'
int  rampaS    = (props.getProperty('rampa_s') ?: '120') as int
int  tasaPico  = (props.getProperty('tasa_pico') ?: '8000') as int
// Si es true, las solicitudes de los conflictos cuentan dentro de la tasa objetivo (el total de reservas/min se mantiene en tasa_pico).
boolean descuentaConf = (props.getProperty('descuenta_conflictos') ?: 'false') == 'true'
// EXP-3 (ataques de reventa). Sin estas propiedades el calendario y la bitácora son exactamente los de EXP-1/EXP-2.
int  ataquesNormal = (props.getProperty('ataques_normal') ?: '0') as int     // ataques al azar en la fase de tráfico normal
int  ataquesPico   = (props.getProperty('ataques_pico') ?: '0') as int       // ataques al azar en la fase de pico
int  botsPorAtaque = (props.getProperty('bots_por_ataque') ?: '100') as int  // 100 IP y 100 cuentas por ataque
int  solBotMin     = (props.getProperty('solicitudes_bot_por_min') ?: '10') as int
int  duracionMaxAtaqueS = (props.getProperty('duracion_max_ataque_s') ?: '60') as int   // tope de cada bot si nadie lo revoca
int  ataqueDesdeS  = (props.getProperty('ataque_normal_desde_s') ?: '0') as int         // los ataques "normales" empiezan tras este calentamiento previo
boolean hayAtaques = ataquesNormal + ataquesPico > 0
boolean ipSim = hayAtaques || (props.getProperty('ip_simuladas') ?: 'false') == 'true'  // X-Forwarded-For: una IP por comprador legítimo
String host    = props.getProperty('host') ?: 'localhost:30080'
String bitacora = props.getProperty('bitacora') ?: 'bitacora.csv'
String ejecJson = props.getProperty('ejecucion_json') ?: 'ejecucion.json'

def rnd = new Random(semilla)
long t0 = System.currentTimeMillis() + 3000          // arranque en 3 s para que todos los hilos estén listos
long finTraficoMs = (calentS + traficoS) * 1000L

def cola = new PriorityBlockingQueue<Map>(20000, { a, b -> a.t <=> b.t } as Comparator)
def idSolic = new java.util.concurrent.atomic.AtomicLong()
def idComp  = new java.util.concurrent.atomic.AtomicLong()

// Asientos "frescos" para llegadas normales: permutación con semilla de 1..100000
def frescos = (1..100000).toList(); Collections.shuffle(frescos, rnd)
int cursorFresco = 0
int cursorConflicto = 100001      // bloques de 6 asientos consecutivos para los conflictos

double factorConf = descuentaConf ? (1.0 + pConf * 7.5) : 1.0     // solicitudes promedio por llegada (5..10 por conflicto)
def tasaEn = { double tMs ->
    if (perfil != 'rampa' || tMs < calentS * 1000.0) return (double) tasaMin
    double x = (tMs - calentS * 1000.0) / (rampaS * 1000.0)
    return x >= 1.0 ? (double) tasaPico : tasaMin + (tasaPico - tasaMin) * x
}
double t = 0
int llegadas = 0, conflictos = 0
while (true) {
    t += -Math.log(1.0 - rnd.nextDouble()) / (tasaEn(t) / factorConf / 60000.0)   // llegadas de Poisson (tasa variable en la rampa)
    if (t >= finTraficoMs) break
    llegadas++
    boolean confirma = rnd.nextDouble() < pConfirma
    long retrasoPago = 5000 + rnd.nextInt(35000)
    cola.add([t: (long) t, tipo: 'NORMAL', grupo: '', solicitud: 'S' + idSolic.incrementAndGet(),
              comprador: 'c' + idComp.incrementAndGet(), asientos: [frescos[cursorFresco++]],
              confirma: confirma, retrasoPago: retrasoPago, esperado: 'OK'])
    if (rnd.nextDouble() < pConf) {                           // 1 de cada 20 llegadas dispara un conflicto
        conflictos++
        int k = 5 + rnd.nextInt(6)                            // 5..10 solicitudes
        int tipoSel = rnd.nextInt(3)
        String tipo = ['CONF_MISMO_ASIENTO', 'CONF_GRUPOS_CRUZADOS', 'CONF_VENDIDO'][tipoSel]
        String grupo = 'G' + conflictos
        int base = cursorConflicto; cursorConflicto += 6
        def barrera = new CyclicBarrier(k)
        for (int i = 0; i < k; i++) {
            List asientos
            if (tipo == 'CONF_GRUPOS_CRUZADOS') {
                int n = 2 + rnd.nextInt(3)                    // grupos de 2 a 4 asientos dentro de una franja de 6
                int ini = base + rnd.nextInt(6 - n + 1)
                asientos = (ini..<(ini + n)).toList()
            } else {
                asientos = [base]
            }
            cola.add([t: (long) t, tipo: tipo, grupo: grupo, solicitud: 'S' + idSolic.incrementAndGet(),
                      comprador: 'c' + idComp.incrementAndGet(), asientos: asientos, barrera: barrera,
                      esperado: tipo == 'CONF_VENDIDO' ? 'NO_DISPONIBLE' : 'UN_GANADOR'])
        }
    }
}

// ---- EXP-3: ataques de reventa en instantes aleatorios (con su propia semilla: el tráfico legítimo no cambia)
def ataquesInfo = []
int botSolicitudesMax = 0
if (hayAtaques) {
    def rndA = new Random(semilla * 31 + 17)
    double ventNormalIni = ataqueDesdeS * 1000.0
    double ventNormalFin = (perfil == 'rampa' ? calentS * 1000.0 : (double) finTraficoMs) - 10000      // deja margen para el primer envío de cada bot
    double ventPicoIni = perfil == 'rampa' ? (calentS + rampaS) * 1000.0 : 0
    double ventPicoFin = finTraficoMs - 10000
    def instantes = []
    if (ataquesNormal > 0 && ventNormalFin > ventNormalIni) ataquesNormal.times { instantes << [(ventNormalIni + rndA.nextDouble() * (ventNormalFin - ventNormalIni)) as long, 'normal'] }
    else if (ataquesNormal > 0) log.warn('EXP-3: no hay ventana de tráfico normal para los ataques')
    if (ataquesPico > 0 && ventPicoFin > ventPicoIni) ataquesPico.times { instantes << [(ventPicoIni + rndA.nextDouble() * (ventPicoFin - ventPicoIni)) as long, 'pico'] }
    else if (ataquesPico > 0) log.warn('EXP-3: no hay ventana de pico para los ataques (use perfil=rampa)')
    instantes.sort { it[0] }
    // Asientos propios de los bots: los frescos que el tráfico normal no usó y los que no tomaron los conflictos (sin reutilizar ninguno).
    def pool = new ArrayList<Integer>(frescos.subList(cursorFresco, frescos.size()))
    if (cursorConflicto <= 130000) pool.addAll((cursorConflicto..130000).toList())
    Collections.shuffle(pool, rndA)
    int totalBots = instantes.size() * botsPorAtaque
    int periodoMs = (60000 / Math.max(1, solBotMin)) as int
    botSolicitudesMax = Math.max(1, Math.min((int) Math.ceil(solBotMin * duracionMaxAtaqueS / 60.0), totalBots > 0 ? (int) (pool.size() / totalBots) : 1))
    if (botSolicitudesMax < Math.ceil(solBotMin * duracionMaxAtaqueS / 60.0))
        log.warn("EXP-3: los asientos libres alcanzan solo para ${botSolicitudesMax} solicitudes por bot (se pedían ${Math.ceil(solBotMin * duracionMaxAtaqueS / 60.0)})")
    int cursorPool = 0
    instantes.eachWithIndex { par, k ->
        int idx = k + 1
        ataquesInfo << [id: 'A' + idx, fase: par[1], t_ms: par[0], inicio_epoch_ms: t0 + par[0], bots: botsPorAtaque]
        for (int b = 1; b <= botsPorAtaque; b++) {
            def seats = pool.subList(cursorPool, cursorPool + botSolicitudesMax).collect { it as int }
            cursorPool += botSolicitudesMax
            cola.add([t: par[0] + rndA.nextInt(periodoMs), tipo: 'ATAQUE_BOT', grupo: 'A' + idx, solicitud: 'S' + idSolic.incrementAndGet(),
                      comprador: "bot-A${idx}-${b}".toString(), ip: "203.0.${idx % 256}.${b}".toString(), asientos: [seats[0]], botSeats: seats,
                      n: 0, periodoMs: periodoMs, esperado: 'ATAQUE'])
        }
    }
    log.info("EXP-3: ${ataquesInfo.size()} ataques x ${botsPorAtaque} bots, hasta ${botSolicitudesMax} solicitudes por bot, asientos libres=${pool.size()}")
}

def w = new BufferedWriter(new FileWriter(bitacora, false))
// Con ataques se AGREGA al final la columna ip (los lectores existentes leen por posición o por nombre y no se alteran).
w.writeLine('solicitud,tipo,grupo,comprador,asientos,t_inicio_ms,t_fin_ms,http,resultado,motivo,bloqueado_en,esperado,cola_s,retraso_ms' + (ipSim ? ',ip' : ''))
w.flush()

props.put('taq.cola', cola)
props.put('taq.t0', t0)
props.put('taq.finTraficoMs', finTraficoMs)
props.put('taq.finSeguimientoMs', finTraficoMs + colaS * 1000L)
props.put('taq.bitacora', w)
props.put('taq.confirmados', new CopyOnWriteArrayList<Integer>())
props.put('taq.idSolic', idSolic)
props.put('taq.idComp', idComp)
props.put('taq.cerrojo', new Object())
props.put('taq.http', java.net.http.HttpClient.newBuilder().version(java.net.http.HttpClient.Version.HTTP_1_1)
          .connectTimeout(java.time.Duration.ofSeconds(3)).build())
props.put('taq.host', host)
props.put('taq.rnd', new Random(semilla + 7919))
props.put('taq.ipSim', ipSim)

new File(ejecJson).text = JsonOutput.prettyPrint(JsonOutput.toJson([
    semilla: semilla, perfil: perfil, rampa_s: rampaS, tasa_pico_por_min: tasaPico, descuenta_conflictos: descuentaConf, tasa_por_min: tasaMin, calentamiento_s: calentS, trafico_s: traficoS,
    inicio_epoch_ms: t0, fin_calentamiento_epoch_ms: t0 + calentS * 1000L,
    fin_trafico_epoch_ms: t0 + finTraficoMs, llegadas_normales: llegadas, conflictos: conflictos,
    p_conflicto: pConf, p_confirma: pConfirma] + (hayAtaques ? [exp3: [ataque_normal_desde_s: ataqueDesdeS, ataques_normal: ataquesNormal, ataques_pico: ataquesPico,
    bots_por_ataque: botsPorAtaque, solicitudes_bot_por_min: solBotMin, duracion_max_ataque_s: duracionMaxAtaqueS,
    solicitudes_max_por_bot: botSolicitudesMax, ataques: ataquesInfo]] : [:])))
log.info("EXP-1 calendario listo: ${llegadas} llegadas, ${conflictos} conflictos, eventos=${cola.size()}")
