package co.uniandes.taq.pasarela;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** Pasarela de pago simulada: latencia fija y sin fallas en EXP-1. */
@RestController
@ConditionalOnProperty(name = "taq.role", havingValue = "pasarela")
public class PasarelaSim {
    private final long ms;
    public PasarelaSim(@Value("${taq.pasarela-ms}") long ms) { this.ms = ms; }

    @PostMapping("/pagar")
    public Map<String, Object> pagar(@RequestBody Map<String, Object> c) throws InterruptedException {
        Thread.sleep(ms);
        return Map.of("resultado", "OK");
    }
}
