<!-- Page layout: navigation tabs, the page content, then the snackbar and confirm dialog -->
<script setup>
import { closeConfirm, confirmState, snackbar } from "../notify.js";
import { currentPage, pageUrl, pages } from "../pages.js";
import { mdiClose } from "../icons.js";

const current = currentPage();
</script>

<template>
	<v-app>
		<v-main>
			<v-tabs :model-value="current" color="primary" density="compact" show-arrows>
				<v-tab v-for="page in pages" :key="page.path" :value="page.path"
					   :href="pageUrl(page.path)" :prepend-icon="page.icon">{{ page.title }}</v-tab>
			</v-tabs>
			<v-divider></v-divider>
			<v-container fluid class="pa-2 pa-sm-4">
				<slot></slot>
			</v-container>
		</v-main>

		<v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="snackbar.timeout">
			{{ snackbar.text }}
			<template #actions>
				<v-btn variant="text" :icon="mdiClose" @click="snackbar.show = false"></v-btn>
			</template>
		</v-snackbar>

		<v-dialog :model-value="confirmState.show" max-width="420" @update:model-value="closeConfirm(false)">
			<v-card>
				<v-card-title>{{ confirmState.title }}</v-card-title>
				<v-card-text>{{ confirmState.text }}</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn @click="closeConfirm(false)">Cancel</v-btn>
					<v-btn :color="confirmState.color" variant="flat" @click="closeConfirm(true)">OK</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	</v-app>
</template>
