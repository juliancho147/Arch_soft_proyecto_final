// Cada hilo toma el siguiente evento vencido, lo ejecuta contra el gateway y anota la bitácora.
import java.util.concurrent.*
import java.net.URI
import java.net.http.*

def cola = props.get('taq.cola') as PriorityBlockingQueue
long t0 = props.get('taq.t0') as long
long finSeg = props.get('taq.finSeguimientoMs') as long
long finTraf = props.get('taq.finTraficoMs') as long
def cerrojo = props.get('taq.cerrojo')

Map ev = null
synchronized (cerrojo) {
    def cab = cola.peek()
    if (cab != null && t0 + cab.t <= System.currentTimeMillis()) ev = cola.poll()
}
if (ev == null) {
    if (cola.isEmpty()) SampleResult.setStopThread(true)
    else Thread.sleep(25)
    SampleResult.setIgnore()
    return 'ocioso'
}

long inicioReal = System.currentTimeMillis()
long retrasoMs = Math.max(0L, inicioReal - (t0 + (ev.t as long)))   // cuánto se atrasó el generador frente al calendario
def http = props.get('taq.http') as HttpClient
String host = props.get('taq.host')
def confirmados = props.get('taq.confirmados')
def bit = props.get('taq.bitacora') as BufferedWriter
def idSolic = props.get('taq.idSolic'); def idComp = props.get('taq.idComp')
def rnd = props.get('taq.rnd') as Random
long ttlS = (props.getProperty('ttl_s') ?: '480') as long

boolean ipSim = props.get('taq.ipSim') as boolean
boolean hayAtaques = props.get('taq.hayAtaques') as boolean
// EXP-3: IP simulada de un comprador legítimo (una por comprador, derivada de c<n>); los bots traen la suya en el evento.
def ipDe = { Map e ->
    if (e.ip) return e.ip as String
    if (!ipSim) return ''
    long n = ((e.comprador as String).replaceAll('[^0-9]', '') ?: '0') as long
    return "10.${(n >> 16) & 255}.${(n >> 8) & 255}.${n & 255}".toString()
}
def enviar = { String ruta, Map cuerpo, String ip = '' ->
    def rb = HttpRequest.newBuilder(URI.create("http://${host}${ruta}")).timeout(java.time.Duration.ofSeconds(10))
        .header('Content-Type', 'application/json')
    if (ip) rb.header('X-Forwarded-For', ip)
    def req = rb.POST(HttpRequest.BodyPublishers.ofString(groovy.json.JsonOutput.toJson(cuerpo))).build()
    long ini = System.currentTimeMillis()
    int cod = 0; Map r = [:]
    try {
        def resp = http.send(req, HttpResponse.BodyHandlers.ofString())
        cod = resp.statusCode()
        r = (new groovy.json.JsonSlurper().parseText(resp.body()) ?: [:]) as Map
    } catch (Exception e) { r = [resultado: 'ERROR_CLIENTE', motivo: e.class.simpleName] }
    return [ini: ini, fin: System.currentTimeMillis(), http: cod, r: r]
}
def anotar = { Map e, Map x ->
    String linea = [e.solicitud, e.tipo, e.grupo ?: '', e.comprador, e.asientos.join('-'), x.ini, x.fin, x.http,
                    x.r.resultado ?: '', x.r.motivo ?: '', x.r.bloqueadoEn ?: '', e.esperado ?: '',
                    (x.ini - t0) / 1000.0, retrasoMs].join(',') + (ipSim ? ',' + ipDe(e) : '') + (hayAtaques ? ',' + (e.tipoAtaque ?: '') : '')
    synchronized (bit) { bit.writeLine(linea); bit.flush() }
}
String etiqueta = ev.tipo == 'CONFIRMAR' ? 'confirmar' : 'reservar'
SampleResult.setSampleLabel(etiqueta + ' ' + ev.tipo)

if (ev.tipo == 'CONFIRMAR') {
    def x = enviar('/api/confirmar', [solicitudId: ev.solicitud, comprador: ev.comprador, asientos: ev.asientos], ipDe(ev))
    anotar(ev, x)
    if (x.r.resultado == 'OK') confirmados.addAll(ev.asientos)
    SampleResult.setSuccessful(x.r.resultado == 'OK')
    return x.r.resultado
}

// Conflictos de venta: se elige un asiento ya vendido; si aún no hay, se degrada a conflicto por el mismo asiento.
if (ev.tipo == 'CONF_VENDIDO') {
    if (confirmados.isEmpty()) { ev.tipo = 'CONF_MISMO_ASIENTO_SIN_VENDIDOS'; ev.esperado = 'UN_GANADOR' }
    else ev.asientos = [confirmados.get(rnd.nextInt(confirmados.size()))]
}
// Las solicitudes de un mismo conflicto salen juntas, al mismo milisegundo.
if (ev.barrera != null) { try { (ev.barrera as CyclicBarrier).await(3, TimeUnit.SECONDS) } catch (Exception ignorada) {} }

SampleResult.sampleStart()
// EXP-3: los atacantes DECLARAN su tipo con la etiqueta tipoAtacante (el tráfico legítimo no la lleva); el detector solo la copia a la evidencia y a las métricas.
def cuerpoReserva = [solicitudId: ev.solicitud, comprador: ev.comprador, evento: 1, asientos: ev.asientos]
if (ev.tipoAtaque) cuerpoReserva.tipoAtacante = ev.tipoAtaque
def x = enviar('/api/reservar', cuerpoReserva, ipDe(ev))
anotar(ev, x)
String res = x.r.resultado

// EXP-3: un atacante (bot, cuenta de granja o acaparador) sigue enviando una reserva cada periodo, con los asientos que le tocan, hasta que lo revocan (403) o se acaban sus asientos.
if (ev.tipo == 'ATAQUE_BOT') {
    boolean revocado = x.http == 403 || res == 'CUENTA_REVOCADA'
    int n = (ev.n as int) + 1
    long ts = (ev.t as long) + (ev.periodoMs as long)
    if (!revocado && n < (ev.botSeats as List).size() && ts <= finSeg)
        cola.add([t: ts, tipo: 'ATAQUE_BOT', tipoAtaque: ev.tipoAtaque, grupo: ev.grupo, solicitud: 'S' + idSolic.incrementAndGet(), comprador: ev.comprador, ip: ev.ip,
                  asientos: (ev.botSeats as List)[n], botSeats: ev.botSeats, n: n, periodoMs: ev.periodoMs, esperado: 'ATAQUE'])
    SampleResult.setSuccessful(true)       // los bots no cuentan como errores de la carga
    SampleResult.setResponseCode(String.valueOf(x.http))
    return res
}
SampleResult.setSuccessful(res == 'OK' || res == 'NO_DISPONIBLE')
SampleResult.setResponseCode(String.valueOf(x.http))

if (ev.tipo == 'NORMAL' && res == 'OK') {
    // Se usa el reloj del cliente (fin de la respuesta): el bloqueo existe desde antes de ese instante.
    long bloq = x.fin
    long ahora = x.fin
    if (ev.confirma) {
        long ts = (ahora - t0) + ev.retrasoPago
        if (ts <= finSeg) cola.add([t: ts, tipo: 'CONFIRMAR', grupo: '', solicitud: ev.solicitud,
            comprador: ev.comprador, asientos: ev.asientos, esperado: 'OK'])
    } else {
        // Abandonado: a los 4 min otro comprador lo pide (se espera rechazo); pasados los 8 min, otro más (se espera éxito).
        [[(ttlS * 500L) as long, 'REVISION_4MIN', 'NO_DISPONIBLE'], [(ttlS + 5) * 1000L, 'REVISION_8MIN', 'OK']].each { d, tipo, esp ->
            long ts = (bloq - t0) + d
            if (ts <= finSeg) cola.add([t: ts, tipo: tipo, grupo: '', solicitud: 'S' + idSolic.incrementAndGet(),
                comprador: 'c' + idComp.incrementAndGet(), asientos: ev.asientos, esperado: esp, origen: ev.solicitud])
        }
    }
}
return res
