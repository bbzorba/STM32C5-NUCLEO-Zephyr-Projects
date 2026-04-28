#include <stdio.h>
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

#define SLEEP_TIME_MS   1000
#define LED0_NODE DT_ALIAS(led0)

static const struct gpio_dt_spec leds[] = {
	GPIO_DT_SPEC_GET(LED0_NODE, gpios),
};

static void configure_leds(const struct gpio_dt_spec *leds, size_t num_leds)
{
	for (size_t i = 0; i < num_leds; i++) {
		if (!gpio_is_ready_dt(&leds[i])) {
			printf("LED%u GPIO device not ready\n", (unsigned)i);
			return;
		}
		gpio_pin_configure_dt(&leds[i], GPIO_OUTPUT_INACTIVE);
	}
}

int main(void)
{	
	configure_leds(leds, ARRAY_SIZE(leds));

	while (1) {
		for (size_t i = 0; i < ARRAY_SIZE(leds); i++) {
			(void)gpio_pin_toggle_dt(&leds[i]);
		}

		k_msleep(SLEEP_TIME_MS);
	}
	return 0;
}
