<script lang="ts">
	import logo from '$lib/assets/netlink-logo.png';

	interface Props {
		height?: number;
		width?: number;
	}

	let { height = 200, width = 200 }: Props = $props();
</script>

<img class="c" {height} {width} src={logo} alt="Netlink Aegis icon" data-testid="logo-image" />
