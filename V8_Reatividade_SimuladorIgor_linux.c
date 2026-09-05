#include<stdio.h>
#include<stdlib.h>
#include<string.h>
#include<math.h>
#include<time.h>
#include<unistd.h>

// Substituir funções do conio.h para Linux
#define getch() getchar()
#define kbhit() 0  // Sempre retorna 0 (sem tecla pressionada)
void system_color() { /* Função vazia - sem cores no Linux */ }

// Prototipos: usadas em CalculaDeltaI(), que e definida antes delas
void atualizadadosXe(void);
void atualizadadosXeg(void);

// Injecao nao-interativa de transiente de carga (via linha de comando).
// O caminho interativo original (digitar "v") permanece intacto; os dois
// caminhos chamam os mesmos helpers AplicaRunback()/AplicaRampa().
typedef enum {
TR_NENHUM = 0,
TR_RUNBACK_BAP,   // desarme da bomba de agua de alimentacao principal -> 300 MW
TR_RUNBACK_CIRC,  // desarme da bomba de agua de circulacao -> 400 MW
TR_RUNBACK_400,
TR_RUNBACK_300,
TR_RUNBACK_150,
TR_RAMPA          // variacao lenta: --alvo=<MW> --taxa=<MW/min>
} TipoTransiente;

TipoTransiente transienteTipo = TR_NENHUM;
int tTransiente = 10;        // minuto de aplicacao do transiente
int transienteAplicado = 0;
double tmax = 700000;        // limite de horizonte da simulacao (minutos)
float argAlvo = 0;
float argTaxa = 0;

float Tref;
float Tmedantes;
float Tmed;
float VariacaoTmed;
float DeltaIantes;
float DeltaI;
float AlvoDeltaI;
float DesvioDeltaI;
float VariacaoDeltaI;
float Cboro;
float Cboro1;
int PosicaoBarra;
float DeltaT;
int DeltaBarra;
float Vazao;
float Vagua;
float VaguaTemp;
float t1;
float t2;
float v1;
float v2;
float a;
float b;
int tempo;
float t;
float ty;
int Retira1passo;
int correcao;
float valor;
int aux;
float razao;
float Msrr;
float alfaboro;
float alfamoderador;
float thom;
float betaeff;
float Ptopo;
float Ptopo0;
float Pbase;
float Pbase0;
float Pbase1;
char termino[10];
float erazao;
float Deltaro;
int i;
float Trx;
float lambda;
float inversoTrx;
float DeltaPbase;
float DeltaPtopo;
float Pot;
int tempodilute;
int x;
int diferenca;
float taxatempreal;
int taxatemp;
float y;
float Vboro;
float VazaoBoro;
float LimiteInsercao;

// Variáveis do Xe
double Nxeb;
double Nxeg;
double Nxe0;
double Nxeg0;
double NxeAntes;
double lambdaXe;
double sigmaXe;
double Fnb;
double Fnb0;
double Fng;
double Fng0;
double gamaI;
double Sigmaf;
double gamaXe;
double lambdaI;
float ConvertXe_Ro;
float Ro;
float RoAntes;
double Ni0;
double Nig0;
float PbaseAntes;
double Nib;
double Nig;
int z;
int tXe;
float PotAntes;
float erro;
float DefPotAntes;
float DefPot;

// Variáveis da variação de carga
char TipoVariacao[16];
char Runback[16];
char funcaocarga[16];
float PotAlvo;
int Runbackmanual;
float AlvoTurbina;
float AlvoTref;
float TaxaTurbina;
float ModuloTref;
float ModuloTaxa;
float PotTurbina;
float PotTurbinaTemp;
int BD;


void GravaDados() {
FILE *arquivo;
arquivo=fopen("Modelagem_Reator.txt", "a");
if(arquivo == NULL) {
printf("Problemas na abertura do arquivo!\n");
exit(1); }
else {
fprintf(arquivo, "%.0f       %.2f     %.1f          %.1f      %.3f        %.0f       %d     %.0f\n", t, Pot, PotTurbina, Tmed, DeltaI, Cboro, PosicaoBarra, VaguaTemp);
}
fclose(arquivo);
return;
}

// Helpers extraidos de VariacaodeCarga(): mesmo estado para o caminho
// interativo e para a injecao automatica.

void AplicaRunback(float trefNovo, float alvoTrefNovo) {
Tref=trefNovo;
AlvoTref=alvoTrefNovo;
PotAlvo=(Tref-291.7)/0.113;
y=t;
ty=t;
tXe=0;
RoAntes=Ro;
Nig0=Nig;
Nxeg0=Nxeg;
return;
}

void AplicaRampa(float alvoTurbina, float taxa) {
AlvoTurbina=alvoTurbina;
TaxaTurbina=taxa;
AlvoTref=291.7+(0.0173846*AlvoTurbina);
ModuloTref=(AlvoTref-Tref);
ModuloTaxa=TaxaTurbina;
if (AlvoTref<Tref) {

TaxaTurbina=-TaxaTurbina;

ModuloTref=-(AlvoTref-Tref);
}
y=t;
ty=t;
tXe=0;
RoAntes=Ro;
Nig0=Nig;
Nxeg0=Nxeg;
return;
}

// Aplica o transiente escolhido por linha de comando, com as mesmas
// guardas de potencia usadas no menu interativo.
void AplicaTransienteAuto() {
switch (transienteTipo) {
case TR_RUNBACK_BAP:
if (PotTurbina>301) { AplicaRunback(296.92,296.92); }
break;
case TR_RUNBACK_CIRC:
if (PotTurbina>401) { AplicaRunback(298.65,298.65); }
break;
case TR_RUNBACK_400:
if (PotTurbina>401) { AplicaRunback(298.65,298.5); }
break;
case TR_RUNBACK_300:
if (PotTurbina>301) { AplicaRunback(296.92,296.92); }
break;
case TR_RUNBACK_150:
if (PotTurbina>150) { AplicaRunback(294.31,294.31); }
break;
case TR_RAMPA:
AplicaRampa(argAlvo,argTaxa);
break;
default:
break;
}
return;
}

void VariacaodeCarga() {

printf("\n\nVariacao de Carga Rapida ou Lenta%c (r/l): ",63);
scanf ("%15s", TipoVariacao);

if (strcmp (TipoVariacao,"r")==0) {

printf("\n\nDesarme Bomba de Agua de Agua de Alimentacao Principal%c (s/n): ",63);
scanf ("%15s", Runback);
if (strcmp (Runback,"s")==0) {
if (PotTurbina>301) {
printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO DESARME DA BOMBA DE AGUA DE ALIMENTACAO PRINCIPAL");
printf("\nPOTENCIA DA TURBINA: 300MW");
printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN",37);
AplicaRunback(296.92,296.92);
}
else {
printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO");}
return;
}

printf("\n\nDesarme Bomba de Agua de Circulacao%c (s/n): ",63);
scanf ("%15s", Runback);
if (strcmp (Runback,"s")==0) {
if (PotTurbina>401) {
printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO DESARME DA BOMBA DE AGUA DE CIRCULACAO");
printf("\nPOTENCIA DA TURBINA: 400MW");
printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN",37);
AplicaRunback(298.65,298.65);
}
else {
printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO");}
return;
}

printf("\n\nReducao Rapida de Carga Manual%c (400/300/150 ou n para nao): ",63);
scanf ("%d", &Runbackmanual);

if (Runbackmanual==400) {
if (PotTurbina>401) {
printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO RUNBACK PARA 400 MW");
printf("\nPOTENCIA DA TURBINA: 400MW");
printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN",37);
AplicaRunback(298.65,298.5); // AlvoTref=298.5 e do original (aparente typo, preservado)
}
else {
printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO");}
return;
}

if (Runbackmanual==300) {
if (PotTurbina>301) {
printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO RUNBACK PARA 300 MW");
printf("\nPOTENCIA DA TURBINA: 300MW");
printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN",37);
AplicaRunback(296.92,296.92);
}
else {
printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO");}
return;
}

if (Runbackmanual==150) {
if (PotTurbina>150) {
printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO RUNBACK PARA 150 MW");
printf("\nPOTENCIA DA TURBINA: 150MW");
printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN",37);
AplicaRunback(294.31,294.31);
}
else {
printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO");}
return;
}
}

if (strcmp (TipoVariacao,"l")==0) {

printf("\n\nDigite o Valor Alvo de Carga na Turbina em MW: ");
scanf ("%f", &AlvoTurbina);

printf("\nDigite a Taxa de Variacao de Carga na Turbina em MW/min: ");
scanf ("%f", &TaxaTurbina);

AplicaRampa(AlvoTurbina,TaxaTurbina);
}
}


void CalculaAlvoDeltaI() {

//if (Cboro>=1440) {
//AlvoDeltaI= (71.43-Pot)/28.57; }

if (Cboro>=1080) {
AlvoDeltaI= Pot/100; } //(71.43-Pot)/28.57; }

//if (Cboro<1440 && Cboro>=1080) {
//AlvoDeltaI= (57.14-Pot)/28.57; }

if (Cboro<1080 && Cboro>=720) {
AlvoDeltaI= (57.14-Pot)/28.57; }

//if (Cboro<1080 && Cboro>=720) {
//AlvoDeltaI= (42.86-Pot)/28.57; }

//if (Cboro<720 && Cboro>=360) {
//AlvoDeltaI= (28.57-Pot)/28.57; }

//if (Cboro<360) {
//AlvoDeltaI= (14.29-Pot)/28.57; }

if (Cboro<720) {
AlvoDeltaI= (42.86-Pot)/28.57; }

return;
}


void CalculaDeltaI() {


DeltaI=Ptopo-Pbase;
DesvioDeltaI=DeltaI-AlvoDeltaI;
DeltaIantes=DeltaI;
printf("\n\nPbase: %f", Pbase);
printf("\n\nPtopo: %f", Ptopo);
//printf("\n\nPbaseAntes: %f", PbaseAntes);
printf("\n\nPbase/PbaseAntes: %f", Pbase/PbaseAntes);
printf("\n\nerro: %f", erro);
Fnb=Fnb0*(Pbase/PbaseAntes); //((Pbase/PbaseAntes)-erro)
printf("\n\nFnb: %f", Fnb);

//printf("\nPotencia na Base do Reator Antes da Oscilacao do Xe: %f%c",Pbase,37);
//printf("\nPotencia no Topo do Reator Antes da Oscilacao do Xe: %f%c",Ptopo,37);
printf("\nDelta I Antes da Oscilacao do Xe: %f",DeltaI);



// EQUAÇÃO DO XENONIO E IODO- BASE

NxeAntes=Nxeb;

Nib=Ni0*pow(2.7182818282,((-lambdaI)*(z*60)))+(gamaI*Sigmaf*Fnb)*(1-pow(2.7182818282,((-lambdaI)*(z*60))))/lambdaI;

Nxeb=(Nxe0*(pow(2.7182818282,(-(lambdaXe+sigmaXe*Fnb)*(z*60)))))+((gamaI+gamaXe)*Sigmaf*Fnb*(1-(pow(2.7182818282,(-(lambdaXe+sigmaXe*Fnb)*(z*60)))))/(lambdaXe+sigmaXe*Fnb))+((gamaI*Sigmaf*Fnb-lambdaI*Ni0)*((pow(2.7182818282,(-(lambdaXe+sigmaXe*Fnb)*(z*60))))-(pow(2.7182818282,(-(lambdaI*(z*60))))))/(lambdaXe-lambdaI+sigmaXe*Fnb));

//printf("\n\nValor da concentracao do Iodo: %f", Nib);
//printf("\n\nValor da concentracao do Xe: %f", Nxeb);

// REGRA DE CONVERSÃO DA CONCENTRAÇÃO DE Xe PARA REATIVIDADE - BASE

RoAntes=NxeAntes*ConvertXe_Ro;
Ro=Nxeb*ConvertXe_Ro;
printf("\n\nRoAntes: %f", RoAntes);
printf("\n\nRo: %f", Ro);
Deltaro=Ro-RoAntes;
if (Deltaro>400) {
Deltaro=400; }
if ((Deltaro<0.0001 && Deltaro>-0.0001) || DeltaI==0) {
Deltaro=0;
}
//printf("\nValor de Reatividade Devido ao Xe: %f", Ro);
printf("\nValor do Delta de Reatividade Devido ao Xe: %f\n", Deltaro);

// ALTERAÇÃO Pbase

if (Deltaro!=0) {
Trx=(betaeff-Deltaro)/(lambda*Deltaro);
printf("\nTrx: %f\n",Trx);
Pbase0=Pbase;
inversoTrx=1/Trx;
Pbase=Pbase*pow(2.72,inversoTrx);
if (Pbase<0) {
Pbase=0; }
DeltaPbase=Pbase-Pbase0;
Ptopo=Ptopo-DeltaPbase;
if (Ptopo<0) {
Ptopo=0; }
}

// NOVO DELTA I

DeltaI=Ptopo-Pbase;
DesvioDeltaI=DeltaI-AlvoDeltaI;
VariacaoDeltaI=DeltaI-DeltaIantes;

printf("\nPotencia na Base do Reator Apos a Oscilacao do Xe: %f%c",Pbase,37);
printf("\nPotencia no Topo do Reator Apos a Oscilacao do Xe: %f%c",Ptopo,37);
//printf("\nPotencia no Topo do Reator Apos a Oscilacao do Xe: %f%c",Ptopo,37);
printf("\nDelta I Apos a Oscilacao do Xe: %f\n",DeltaI);

//printf("\nNxeAntes: %f\n",NxeAntes);
//printf("\nNxeb: %f\n",Nxeb);


if ((Nxeb-NxeAntes)<1000 && (Nxeb-NxeAntes)>-1000) {

atualizadadosXe();
}


// ALTERA A POTENCIA DO REATOR DEVIDO AO EFEITO GLOBAL DO XE DEVIDO A TRANSIENTES DE CARGA
//if (tXe<4320) {
printf("\n\nFngAntes: %f", Fng);
Fng=Fng0*(Pot/PotAntes);
printf("\n\nPot/PotAntes: %f", Pot/PotAntes);
printf("\n\nFng: %f", Fng);
printf("\n\ntXe: %d", tXe);

NxeAntes=Nxeg;

Nig=Nig0*pow(2.7182818282,((-lambdaI)*(tXe*60)))+(gamaI*Sigmaf*Fng)*(1-pow(2.7182818282,((-lambdaI)*(tXe*60))))/lambdaI;

Nxeg=(Nxeg0*(pow(2.7182818282,(-(lambdaXe+sigmaXe*Fng)*(tXe*60)))))+((gamaI+gamaXe)*Sigmaf*Fng*(1-(pow(2.7182818282,(-(lambdaXe+sigmaXe*Fng)*(tXe*60)))))/(lambdaXe+sigmaXe*Fng))+((gamaI*Sigmaf*Fng-lambdaI*Nig0)*((pow(2.7182818282,(-(lambdaXe+sigmaXe*Fng)*(tXe*60))))-(pow(2.7182818282,(-(lambdaI*(tXe*60))))))/(lambdaXe-lambdaI+sigmaXe*Fng));

RoAntes=NxeAntes*ConvertXe_Ro;
Ro=Nxeg*ConvertXe_Ro;
printf("\n\nRoAntes: %f", RoAntes);
printf("\n\nRo: %f", Ro);
Deltaro=Ro-RoAntes;
if (Deltaro>400) {
Deltaro=400; }
if ((Deltaro<0.0001 && Deltaro>-0.0001) || DeltaI==0) {
Deltaro=0;
}
// Defeito de Potência Antes da Variação Devido ao Xe
DefPotAntes=(Cboro-3806.7024)*Pot/150.88;

//printf("\nValor de Reatividade Devido ao Xe: %f", Ro);
printf("\nValor do Delta de Reatividade Devido ao Xe: %f\n", Deltaro);
if (Deltaro!=0) {
Trx=(betaeff-Deltaro)/(lambda*Deltaro);
printf("\nTrxPot: %f\n",Trx);
printf("\nPotencia do Reator Antes do Variacao do Xe: %f\n",Pot);
inversoTrx=1/Trx;
Pot=Pot*pow(2.72,inversoTrx);
if (Pot<0) {
Pot=0; }
Ptopo=(2*Pot+DeltaI)/2;
Pbase=(2*Pot-DeltaI)/2;
PbaseAntes=Pot;
if (Pot!=0) {
erro=DeltaI*((1/PotAntes)-(1/Pot)); }
printf("\nPotencia variando devido ao Xe: %f\n",Pot);
DefPot=(Cboro-3806.7024)*Pot/150.88;
printf("\nTemperatura Media Antes da Variacao do Xe: %.1f\n",Tmed);
Tmed=Tmed+((DefPot-DefPotAntes)/alfamoderador);
printf("\nTemperatura Media Apos da Variacao de Potencia Devido ao Xe: %.1f\n",Tmed);
//getch();
}
if (((Nxeb-NxeAntes)<1000 && (Nxeb-NxeAntes)>-1000) || tXe>=4320) {

atualizadadosXeg();

}

return;
}

void atualizadadosXe() {

printf("\n\nATUALIZA DADOS");
z=0;
RoAntes=Ro;
Ni0=Nib;
Nxe0=Nxeb;
return;
}

void atualizadadosXeg() {

printf("\n\nATUALIZA DADOS GLOBAIS");
tXe=0;
RoAntes=Ro;
Nig0=Nig;
Nxeg0=Nxeg;
return;
}


// Funcoes Diluicao

void CorrigeTmedDiluicao() {
printf("\n\nVolume de agua pura adicionado: %.0f",Vagua);
Cboro1=Cboro;
printf("\n\nConcentracao de Boro do SRR Antes da Diluicao: %f ppm",Cboro1);
razao=Vagua/Msrr;
erazao=pow(2.72,razao);
Cboro=Cboro/(erazao);
printf("\nConcentracao de Boro do SRR Apos a Diluicao: %f ppm",Cboro);
// ATUALIZACAO DOS PARAMETROS QUE VARIAM COM A CONCENTRACAO DE BORO
printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d\n",taxatemp);
alfamoderador=0.02849*Cboro-75.02849;
printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C",alfamoderador);
alfaboro=0.0005363*Cboro-7.285363;
printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n",alfaboro);
v1=-0.05307*Cboro+100.5307;
if (v1<=0) {
v1=5; }
printf("\nValor da Vazao de Diluicao Minima: %.0f lpm",v1);
v2=-0.24022*Cboro+452.24022;
if (v2<=0) {
v2=10; }
printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", v2);
a=2*v1;
printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f",a);
b=v1;
printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n",b);
printf("\nPosicao do Banco de Controle D: %d\n",PosicaoBarra);
// FIM DA ATUALIZACAO CBORO


Deltaro=(Cboro-Cboro1)*alfaboro;
printf("\n\nVariacao de Reatividade Devido a Diluicao: %f pcm",Deltaro);
printf("\n\n\nATENCAO: O SRR ESTA AQUECENDO DEVIDO A DILUICAO\n\n");
for (i=thom; i>0; i--) {
Tmedantes=Tmed;
Tmed=(-(Deltaro/thom)/alfamoderador)+Tmed;
aux=thom+1-i;
printf("\nTmed%d: %f °C",aux,Tmed);
DeltaT=Tmed-Tref;
VariacaoTmed=Tmed-Tmedantes;
//sleep(1);
t=t+1;
z=z+1;
tXe=tXe+1;
}
printf("\n\n\nA ESTABILIZACAO DA TEMPERATURA DO SRR FOI ATINGIDA\n\n");
printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",Tmed,DeltaT);
return;}

void CorrigeDeltaIDiluicao() {
Trx=(betaeff-Deltaro)/(lambda*Deltaro);
printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f",Trx);
Pbase0=Pbase;
printf("\nPotencia na Base do Reator Antes da Diluicao: %f%c",Pbase,37);
inversoTrx=1/Trx;
Pbase1=Pbase*pow(2.72,inversoTrx);
DeltaPbase=(Pbase1-Pbase0)*0.9;
Pbase=Pbase+DeltaPbase;
if (Pbase<0) {
Pbase=0; }
printf("\nPotencia na Base do Reator Apos da Diluicao: %f%c",Pbase,37);
Ptopo=Ptopo-DeltaPbase;
if (Ptopo<0) {
Ptopo=0; }
DeltaI=Ptopo-Pbase;
DesvioDeltaI=DeltaI-AlvoDeltaI;

// CALCULA DELTA I Xe APÓS DILUIÇÃO

    CalculaDeltaI();

return;
}

// Funcões Boração

void CorrigeTmedBoracao() {
printf("\n\nVolume de Boro adicionado: %.0f",Vboro);
Cboro1=Cboro;
printf("\n\nConcentracao de Boro do SRR Antes da Boracao: %f ppm",Cboro1);
razao=-Vboro/Msrr;
erazao=pow(2.72,razao);
Cboro=7200-(7200-Cboro)*erazao;
printf("\nConcentracao de Boro do SRR Apos a Boracao: %f ppm",Cboro);

// ATUALIZACAO DOS PARAMETROS QUE VARIAM COM A CONCENTRACAO DE BORO
taxatempreal=(2601-Cboro)/6.31; // (2619-Cboro)/6.16;
taxatemp=taxatempreal; //tempo de redução de 0,1ºC
printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d\n",taxatemp);
alfamoderador=0.02849*Cboro-75.02849;
printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C",alfamoderador);
alfaboro=0.0005363*Cboro-7.285363;
printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n",alfaboro);
v1=-0.05307*Cboro+100.5307;
if (v1<=0) {
v1=5; }
printf("\nValor da Vazao de Diluicao Minima: %.0f lpm",v1);
v2=-0.24022*Cboro+452.24022;
if (v2<=0) {
v2=10; }
printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", v2);
a=2*v1;
printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f",a);
b=v1;
printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n",b);
printf("\nPosicao do Banco de Controle D: %d\n",PosicaoBarra);
// FIM DA ATUALIZACAO CBORO


Deltaro=(Cboro-Cboro1)*alfaboro;
printf("\n\nVariacao de Reatividade Devido a Boracao: %f pcm",Deltaro);
printf("\n\n\nATENCAO: O SRR ESTA RESFRIANDO DEVIDO A BORACAO\n\n");
for (i=thom; i>0; i--) {
Tmedantes=Tmed;
Tmed=(-(Deltaro/thom)/alfamoderador)+Tmed;
aux=thom+1-i;
printf("\nTmed%d: %f °C",aux,Tmed);
DeltaT=Tmed-Tref;
VariacaoTmed=Tmed-Tmedantes;
//sleep(1);
t=t+1;
z=z+1;
tXe=tXe+1;
}
printf("\n\n\nA ESTABILIZACAO DA TEMPERATURA DO SRR FOI ATINGIDA\n\n");
printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",Tmed,DeltaT);
return;}

void CorrigeDeltaIBoracao() {
Trx=(betaeff-Deltaro)/(lambda*Deltaro);
printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f",Trx);
Pbase0=Pbase;
printf("\nPotencia na Base do Reator Antes da Boracao: %f%c",Pbase,37);
inversoTrx=1/Trx;
Pbase1=Pbase*pow(2.72,inversoTrx);
DeltaPbase=(Pbase1-Pbase0)*1.6;
Pbase=Pbase+DeltaPbase;
if (Pbase<0) {
Pbase=0; }
printf("\nPotencia na Base do Reator Apos da Boracao: %f%c",Pbase,37);
Ptopo=Ptopo-DeltaPbase;
if (Ptopo<0) {
Ptopo=0; }
DeltaI=Ptopo-Pbase;
DesvioDeltaI=DeltaI-AlvoDeltaI;


// CALCULA DELTA I Xe APÓS BORAÇÃO



    CalculaDeltaI();



return;
}


// Funcoes DeltaBarra

void CorrigeTmedDeltaBarra() {

if (PosicaoBarra>=100) {
Deltaro=6.5*DeltaBarra;
}
else {
Deltaro=20*DeltaBarra;
}
DeltaBarra=0;
printf("\n\nVARIACAO DE REATIVIDADE DEVIDO A MOVIMENTACAO DE BARRA: %f pcm",Deltaro);
Tmedantes=Tmed;
printf("\nTemperatura Media antes da Movimentacao de Barra: %f °C",Tmed);
Tmed=(-(Deltaro/alfamoderador)) + Tmed;
DeltaT=Tmed-Tref;
VariacaoTmed=Tmed-Tmedantes;
//sleep(1);
t=t+2;
z=z+2;
tXe=tXe+2;
printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",Tmed,DeltaT);
return; }

void CorrigeDeltaIDeltaBarra() {
Trx=(betaeff-Deltaro)/(lambda*Deltaro);
printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f",Trx);
Ptopo0=Ptopo;
printf("\nPotencia no Topo do Reator Antes da Movimentacao de Barra: %f%c",Ptopo,37);
inversoTrx=1/Trx;
Ptopo=Ptopo*pow(2,inversoTrx);
DeltaPtopo=Ptopo-Ptopo0;
printf("\nPotencia no Topo do Reator Apos da Movimentacao de Barra: %f%c",Ptopo,37);
Pbase=Pbase-DeltaPtopo;
DeltaI=Ptopo-Pbase;
DesvioDeltaI=DeltaI-AlvoDeltaI;
// CALCULA DELTA I Xe APÓS DILUIÇÃO




    CalculaDeltaI();


return;
}



// Funcao Compensacao da Queima

void CompensacaoQueima() {

    if (DeltaT<-0.1)  {
           // if (VariacaoTmed <=0) {

        if ((VariacaoDeltaI>=0 || DeltaT<-0.3) || (PosicaoBarra>=222 || DesvioDeltaI>-3)) {

            if (DeltaT>=t1) {
            Vazao=v1;
            printf("\n\nDeltaT: %f\n\n", DeltaT);
            printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm",Vazao);
            tempo=t;        }
            if (DeltaT<=t2) {
            Vazao=v2;
            printf("\n\nDeltaT: %f\n\n", DeltaT);
            printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm",Vazao);
            tempo=t;        }
            if (DeltaT>t2 && DeltaT<t1) {
            Vazao=(-a*DeltaT)+b;
            printf("\n\nDeltaT: %f\n\n", DeltaT);
            printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm",Vazao);
            tempo=t;        }
            //sleep(1); //tempodilute
            t=t+tempodilute;
            z=z+tempodilute;
            tXe=tXe+tempodilute;
            printf("\n\nDiluicao Encerrada");
            Vagua=Vazao*(t-tempo);
            Vazao=0;
            VaguaTemp=Vagua+VaguaTemp;
            CorrigeTmedDiluicao();
            CorrigeDeltaIDiluicao();
                    }
            if ((DesvioDeltaI<0 && (VariacaoDeltaI<=0 || DeltaT<-0.3) && PosicaoBarra<222)) {
            printf("\n\nCOMPENSACAO DA QUEIMA POR RETIRADA DE BARRA\n\n");
            printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
            PosicaoBarra=PosicaoBarra+1;
            printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);
            DeltaBarra=1;
            CorrigeTmedDeltaBarra();
            CorrigeDeltaIDeltaBarra(); }

            if ((DeltaT<-0.8) && (DesvioDeltaI>=0 || PosicaoBarra>=222)) {
            Vazao=v2;
            printf("\n\nDeltaT: %f\n\n", DeltaT);
            printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm",Vazao);
            tempo=t;
            //sleep(1); //tempodilute
            t=t+tempodilute;
            z=z+tempodilute;
            tXe=tXe+tempodilute;
            printf("\n\nDiluicao Encerrada");
            Vagua=Vazao*(t-tempo);
            Vazao=0;
            VaguaTemp=Vagua+VaguaTemp;
            CorrigeTmedDiluicao();
            CorrigeDeltaIDiluicao();
            }
            if ((DeltaT<-0.8) && (DesvioDeltaI<4) && (PosicaoBarra<222)) {
            printf("\n\nCORRECAO DA TEMPERATURA MEDIA POR RETIRADA DE BARRA\n\n");
            printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
            PosicaoBarra=PosicaoBarra+2;
            printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);
            DeltaBarra=2;
            CorrigeTmedDeltaBarra();
            CorrigeDeltaIDeltaBarra(); }

                                            }
return;
                                                   }

// Funcao corrige delta I

void Corrige_DeltaI() {
if ((DesvioDeltaI>=0 && DeltaT<=0.4) || (DesvioDeltaI>4.5 && DeltaT<2)) {
if (DeltaT>=t1) {
Vazao=2*v1;
printf("\n\nDeltaT: %f\n\n", DeltaT);
printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm",Vazao);
tempo=t;        }
if (DeltaT<=t2) {
Vazao=2*v2;
printf("\n\nDeltaT: %f\n\n", DeltaT);
printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm",Vazao);
tempo=t;        }
if (DeltaT>t2 && DeltaT<t1) {
Vazao=2*((-a*DeltaT)+b);
printf("\n\nDeltaT: %f\n\n", DeltaT);
printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm",Vazao);
tempo=t;        }
//sleep(1); //tempodilute
t=t+tempodilute;
z=z+tempodilute;
tXe=tXe+tempodilute;
printf("\n\nDiluicao Encerrada");
Vagua=Vazao*(t-tempo);
Vazao=0;
VaguaTemp=Vagua+VaguaTemp;
CorrigeTmedDiluicao();
CorrigeDeltaIDiluicao();
}
if (DesvioDeltaI<0 && DeltaT<0.8 && PosicaoBarra<222) {

printf("\n\nCORRECAO DO DELTA I POR RETIRADA DE BARRA\n\n");
printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
PosicaoBarra=PosicaoBarra+1;
printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);
DeltaBarra=DeltaBarra+1;
CorrigeTmedDeltaBarra();
CorrigeDeltaIDeltaBarra(); }

if ((DeltaT>-0.6) && (DesvioDeltaI>4.5) && (PosicaoBarra>(LimiteInsercao+11) || DesvioDeltaI>5)) {

printf("\n\nCORRECAO DA DELTA I POR INSERCAO DE BARRA\n\n");
printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
PosicaoBarra=PosicaoBarra-1;
printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);
DeltaBarra=-1;
CorrigeTmedDeltaBarra();
CorrigeDeltaIDeltaBarra();
}


if (((DesvioDeltaI<-4 && PosicaoBarra>=222) && DeltaT>-1) || (DesvioDeltaI<-10 && DeltaT>-3)) {

// Cálculo do Volume de Boro

VazaoBoro=-DesvioDeltaI*6;
if (VazaoBoro>20) {
VazaoBoro=20;
}
Vboro=VazaoBoro*2;

printf("\n\nCORRECAO DO DELTA I POR BORACAO\n\n");

CorrigeTmedBoracao();
CorrigeDeltaIBoracao();


//getch();
}
return;
}




// PROGRAMA PRINCIPAL

int main(int argc, char **argv) {

int ai;
char *val;

// Argumentos opcionais; sem nenhum deles o comportamento e o de antes.
for (ai=1; ai<argc; ai++) {
if (strncmp(argv[ai],"--transiente=",13)==0) {
val=argv[ai]+13;
if (strcmp(val,"runback-bap")==0) { transienteTipo=TR_RUNBACK_BAP; }
else if (strcmp(val,"runback-circ")==0) { transienteTipo=TR_RUNBACK_CIRC; }
else if (strcmp(val,"runback-400")==0) { transienteTipo=TR_RUNBACK_400; }
else if (strcmp(val,"runback-300")==0) { transienteTipo=TR_RUNBACK_300; }
else if (strcmp(val,"runback-150")==0) { transienteTipo=TR_RUNBACK_150; }
else if (strcmp(val,"rampa")==0) { transienteTipo=TR_RAMPA; }
else { fprintf(stderr,"Transiente desconhecido: %s\n",val); return 1; }
}
else if (strncmp(argv[ai],"--alvo=",7)==0) { argAlvo=atof(argv[ai]+7); }
else if (strncmp(argv[ai],"--taxa=",7)==0) { argTaxa=atof(argv[ai]+7); }
else if (strncmp(argv[ai],"--t-transiente=",15)==0) { tTransiente=atoi(argv[ai]+15); }
else if (strncmp(argv[ai],"--tmax=",7)==0) { tmax=atof(argv[ai]+7); }
else { fprintf(stderr,"Argumento desconhecido: %s\n",argv[ai]); return 1; }
}
if (transienteTipo==TR_RAMPA && argTaxa<=0) {
fprintf(stderr,"--transiente=rampa exige --alvo=<MW> e --taxa=<MW/min> positiva\n");
return 1;
}

system_color();
printf("\n\t\t\t\t\t******************************");
printf("\n\t\t\t\t\tCONTROLE AUTOMATICO DO REATOR");
printf("\n\t\t\t\t\t******************************\n");
printf("\t\t\t\t\t");
strcpy(termino, "inicio");
FILE *arquivo;
fflush(stdin);
arquivo=fopen("Modelagem_Reator.txt", "a");
if(arquivo == NULL) {
printf("Problemas na abertura do arquivo!\n");
exit(1); }
else {
//fwrite(&Pot, sizeof(Pot), 1, arquivo);
fprintf(arquivo, "Tempo    Pot Rx    Pot Turbina     Tmed   Delta I  Cboro  Banco D  Volume de Água\n\n\n");

//fwrite(&Pot, sizeof(100),2, arquivo);
}
fclose(arquivo);


//for(i=0; i<29; i++) {
//    printf("%c",177); }

printf("\n\n\nDigite a Potencia Inicial da Turbina em MW (32 a 650MW): ");
scanf("%f",&PotTurbina);
Pot=PotTurbina/6.5;
PotAlvo=Pot;
Tref=0.113*Pot+291.7;
Tmed=Tref;
AlvoTref=Tref;
printf("\nValor da Temperatura Media Inicial do SRR %.1f°C", Tmed);
//scanf("%f",&Tmed);
printf("\n\nDigite o Valor da Concentracao Inicial de Boro (ppm): ");
scanf("%f",&Cboro);
printf("\nDigite a Posicao Inicial do Banco de Controle D (passos): ");
scanf("%d",&PosicaoBarra);
//printf("\nDigite o Valor do Coeficiente de Reatividade do Boro (pcm/ppm): ");
//scanf("%f",&alfaboro);
//printf("\nDigite o Valor do Coeficiente de Temperatura do Moderador (pcm/°C): ");
//scanf("%f",&alfamoderador);
printf("\nDigite o Intervalo de Tempo por Diluicao (minutos): ");
scanf("%d",&tempodilute);
printf("\nDigite o Delta de Temperatura para a Vazao Minima (°C): ");
scanf("%f",&t1);
printf("\nDigite o Delta de Temperatura para a Vazao Maxima (°C): ");
scanf("%f",&t2);
//printf("\nDigite o Valor da Vazao de Diluicao Minima (lpm): ");
//scanf("%d",&v1);
//printf("\nDigite o Valor da Vazao de Diluicao Maxima (lpm): ");
//scanf("%d",&v2);
//printf("\nDigite o Valor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: ");
//scanf("%d",&a);
//printf("\nDigite o Valor do Coeficiente B da Equacao de Diluicao: Vazao= -A.DeltaT + B: ");
//scanf("%d",&b);
Msrr=132440;
//printf("\nDigite o Tempo de Homogeneizacao da Massa do SRR (minutos): ");
//scanf("%f",&thom);
thom=18;
printf("\nDigite o Delta I Inicial: ");
scanf("%f",&DeltaI);
printf("\n\nPARA INSERIR UMA VARIACAO DE CARGA DIGITE v EM QUALQUER MOMENTO DO CICLO DE OPERACAO\n\n\n");


lambda=0.1;  // λ médio;
DeltaT=Tmed-Tref;
t=0;
x=0;
y=0;
ty=0;
if (Cboro>800) {
betaeff=594; } // 594pcm no IDC
else {
betaeff=522; } // 522pcm no FDC
taxatempreal=(2601-Cboro)/6.31; // (2568-Cboro)/6.4;
taxatemp=taxatempreal; //tempo de redução de 0,1ºC
printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d",taxatemp);
alfamoderador=0.02849*Cboro-75.02849;
printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C",alfamoderador);
alfaboro=0.0005363*Cboro-7.285363;
printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n",alfaboro);
v1=-0.05307*Cboro+100.5307;
if (v1<=0) {
v1=5; }
printf("\nValor da Vazao de Diluicao Minima: %.0f lpm",v1);
v2=-0.24022*Cboro+452.24022;
if (v2<=0) {
v2=10; }
printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", v2);
a=2*v1;
printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f",a);
b=v1;
printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n",b);

TaxaTurbina=0;

// PARAMENTROS REFERENTES AO XE NO MAIN

Nxe0=(Pot/100)*3.70461*pow(10,14);//3.70461*pow(10,14);
Nxeb=Nxe0;
Nxeg=Nxe0;
Nxeg0=Nxe0;
Ni0=(Pot/100)*9.589*pow(10,14);;//9.589*pow(10,14);
Nib=Ni0;
Nig=Ni0;
Nig0=Ni0;
lambdaXe=2.116*pow(10,-5);
sigmaXe=2.6*pow(10,-18);
gamaI=0.056;
Sigmaf=0.01;
gamaXe=0.056;
lambdaI=2.92*pow(10,-5);
ConvertXe_Ro=-6.8636*pow(10,-12);

lambda=0.1;
betaeff=594;

Ptopo=(2*Pot+DeltaI)/2;
Pbase=(2*Pot-DeltaI)/2;
Fnb0=5*pow(10,13)*Pot/100;
Fng0=Fnb0;
//Ro=-2542.696533;
RoAntes=Nxe0*ConvertXe_Ro;

PotAntes=Pot;
PbaseAntes=Pot;

z=0;
tXe=0;
erro=0;
VaguaTemp=0;

// PROGRAMA

while (strcmp(termino, "fim") != 0 && t < tmax) { // Loop até fim de ciclo (boro < 8 ppm) ou limite de horizonte (--tmax, default ~486 dias)
//sleep(1);
t=t+1;
z=z+1;
tXe=tXe+1;
Ptopo=(2*Pot+DeltaI)/2;
Pbase=(2*Pot-DeltaI)/2;
// Corrige Tmed conforme a queima
taxatempreal=(2601-Cboro)/6.31;
taxatemp=taxatempreal; //tempo de redução de 0,1ºC
valor=(t/taxatemp);
aux=valor;
if (aux==valor) {
Tmedantes=Tmed;
Tmed=Tmed-0.1;
x=x+1;
DeltaT=Tmed-Tref;
VariacaoTmed=Tmed-Tmedantes;
}
if (aux>x) {
diferenca=aux-x;
Tmedantes=Tmed;
Tmed=Tmed-(0.1*diferenca);
x=aux;
DeltaT=Tmed-Tref;
VariacaoTmed=Tmed-Tmedantes;
} // Fim da correção de Tmed conforme a queima

LimiteInsercao=2.58*(Pot)-85;


// Ajuste da Carga Programada

if (TaxaTurbina!=0) {
while (t>=ty) {
ty=ty+1;
if (ModuloTref>(ModuloTaxa*0.0173846)) {
Tref=Tref+(TaxaTurbina*0.0173846);
PotAlvo=(Tref-291.7)/0.113;
ModuloTref=(AlvoTref-Tref);
if (AlvoTref<Tref) {
ModuloTref=-(AlvoTref-Tref); }
printf("\nModuloTref=%.2f\n",ModuloTref);
}
if (ModuloTref<=(ModuloTaxa*0.0173846)) {
Tref=AlvoTref;
TaxaTurbina=0;
PotAlvo=(Tref-291.7)/0.113;
}
}
}
while (t>=y && (Pot>(PotAlvo+0.015) || (Pot<(PotAlvo-0.015)))) {
y=y+1;
for (i=0; i<500; i++) {
//printf("\n\ni:%d",i);
if (Pot>PotAlvo) {
Pot=Pot-0.01;
Ptopo=(2*Pot+DeltaI)/2;
Pbase=(2*Pot-DeltaI)/2;
PbaseAntes=Pot;
//tXe=0;
if (Pot!=0) {
erro=DeltaI*((1/PotAntes)-(1/Pot)); }
//printf("\n\nErro corrigido: %f",erro);
printf("\n\nPOTENCIA DO REATOR: %f%c",Pot,37);
if (TaxaTurbina!=0) {
PotTurbina=6.5*Pot;
printf("\nPOTENCIA DA TURBINA: %f", PotTurbina); }
}
if (Pot<PotAlvo) {
Pot=Pot+0.01;
Ptopo=(2*Pot+DeltaI)/2;
Pbase=(2*Pot-DeltaI)/2;
PbaseAntes=Pot;
//tXe=0;
printf("\n\nPOTENCIA DO REATOR: %f%c",Pot,37);
if (TaxaTurbina!=0) {
PotTurbina=6.5*Pot;
printf("\nPOTENCIA DA TURBINA: %f", PotTurbina); }
}
if ((Pot<=(PotAlvo+0.015)) && (Pot>=(PotAlvo-0.015))) {
break; }
}
}
CalculaAlvoDeltaI();
CalculaDeltaI();

printf("\n\n\nt=%.0f",t);
//sleep(1);
printf("\nZ=%d",z);
printf("\nPot=%.2f",Pot);
if ((Pot<=(PotAlvo+0.015)) && (Pot>=(PotAlvo-0.015))) {
PotTurbina=6.5*Pot;
printf("\nPotTurbina=%.1f",PotTurbina); }
PotTurbinaTemp=6.5*Pot;
printf("\nPotTurbinaTemp=%.1f",PotTurbinaTemp);
printf("\nAlvoTref=%.2f",AlvoTref);
printf("\nTmed=%.1f",Tmed);
printf("\nTref=%.1f",Tref);
printf("\nAlvo DeltaI=%f",AlvoDeltaI);
printf("\nDeltaI=%f",DeltaI);
printf("\nDesvioDeltaI=%f",DesvioDeltaI);
printf("\nVariacaoDeltaI=%f",VariacaoDeltaI);
printf("\nPosicao Barra=%d",PosicaoBarra);
printf("\nPosicao de referencia BD=%d",BD);
printf("\nCboro=%f\n\n\n",Cboro);

GravaDados();

// Injecao automatica do transiente, no mesmo ponto do laco em que o
// operador digitaria "v" no programa original.
if (transienteTipo!=TR_NENHUM && transienteAplicado==0 && t>=tTransiente) {
transienteAplicado=1;
printf("\n\nTRANSIENTE APLICADO EM t=%.0f\n",t);
AplicaTransienteAuto();
}

if (kbhit()) {
scanf ("%15s", funcaocarga);
if (strcmp (funcaocarga,"v")==0) {
printf("Variacao de Carga");
VariacaodeCarga();  }
}

// CALCULA DELTA I NO LOOP DO MAIN


Ptopo=(2*Pot+DeltaI)/2;
Pbase=(2*Pot-DeltaI)/2;
if (Ptopo<0) {
Ptopo=0; }
#ifdef WIN_ORIGINAL
if (Pbase<0) {
Ptopo=0; } // semantica literal do original .txt (aparente troca de variavel)
#else
if (Pbase<0) {
Pbase=0; } // corrigido: era "Ptopo=0" (aparente troca de variavel)
#endif

BD=0.73*Pot+144;
printf("BD: %d", BD);

if (DeltaT<-0.1) {
CompensacaoQueima(); }



if (DesvioDeltaI>2 || DesvioDeltaI<-2) {
Corrige_DeltaI(); }

if ((DeltaT>0.6) && (DesvioDeltaI>=-2.2) && (PosicaoBarra>(LimiteInsercao+11) || DeltaT>1.5)) {
printf("\n\nCORRECAO DA TEMPERATURA MEDIA POR INSERCAO DE BARRA\n\n");
printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
if (DeltaT<1) {
PosicaoBarra=PosicaoBarra-1;
DeltaBarra=-1;
}
else {
PosicaoBarra=PosicaoBarra-2;
DeltaBarra=-2;
}
printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);

CorrigeTmedDeltaBarra();
CorrigeDeltaIDeltaBarra();
}

if ((DeltaT>0.8) && (DesvioDeltaI<0)) {

// Volume de Boro

VazaoBoro=DeltaT*10;
Vboro=VazaoBoro*4;

printf("\n\nCORRECAO DO DELTA T POR BORACAO\n\n");

CorrigeTmedBoracao();
CorrigeDeltaIBoracao();
}

if (PosicaoBarra<=(LimiteInsercao+10) && PosicaoBarra>LimiteInsercao) {

printf("\n\nALARME ATIVADO: LIMITE DE INSERCAO BAIXO\n\n");

if (DeltaI<0)  {

// Volume de Boro

VazaoBoro=(LimiteInsercao-PosicaoBarra+11)*2;
Vboro=VazaoBoro*2;

printf("\n\nLIMITE DE INSERCAO BAIXO ATINGIDO - BORACAO NORMAL\n\n");

CorrigeTmedBoracao();
CorrigeDeltaIBoracao();
}
}

if (PosicaoBarra<=LimiteInsercao) {

printf("\n\nALARME ATIVADO: LIMITE DE INSERCAO MUITO BAIXO\n\n");

if (DeltaI<0)  {
// Volume de Boro

VazaoBoro=(LimiteInsercao+1-PosicaoBarra)*5;
Vboro=VazaoBoro*2;

printf("\n\nLIMITE DE INSERCAO MUITO BAIXO ATINGIDO - BORACAO DE EMERGENCIA\n\n");

CorrigeTmedBoracao();
CorrigeDeltaIBoracao();
}
}

            if ((PosicaoBarra<(BD-3)) && (DesvioDeltaI<4.2) && (DeltaT<0.8)) {
            printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n");
            printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
            PosicaoBarra=PosicaoBarra+1;
            printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);
            DeltaBarra=1;
            CorrigeTmedDeltaBarra();
            CorrigeDeltaIDeltaBarra(); }

            if ((PosicaoBarra>(BD+10)) && (DesvioDeltaI>=-3) && (DeltaT>-0.4)) {
            printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n");
            printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
            PosicaoBarra=PosicaoBarra-1;
            printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);
            DeltaBarra=-1;
            CorrigeTmedDeltaBarra();
            CorrigeDeltaIDeltaBarra(); }

            if ((PosicaoBarra<(LimiteInsercao+11)) && (DesvioDeltaI<4) && (DeltaT<0.5)) {
            printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n");
            printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
            PosicaoBarra=PosicaoBarra+1;
            printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);
            DeltaBarra=1;
            CorrigeTmedDeltaBarra();
            CorrigeDeltaIDeltaBarra(); }

            if ((PosicaoBarra>220) && (DesvioDeltaI>=-1.5) && (DeltaT>-0.25)) {
            printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n");
            printf("\n\nPosicao Anterior do Banco D: %d passos",PosicaoBarra);
            PosicaoBarra=PosicaoBarra-1;
            printf("\n\nPosicao Atual do Banco D: %d passos\n",PosicaoBarra);
            DeltaBarra=-1;
            CorrigeTmedDeltaBarra();
            CorrigeDeltaIDeltaBarra(); }

//valor=(t/1000);
//aux=valor;
//if (aux==valor) {
//printf("\n\nDigite fim para terminar ou qualquer tecla para continuar: ");
//scanf ("%s", &termino);
//}

if (DesvioDeltaI>5 || DesvioDeltaI<-5) {
printf("\n\n\n\t\t\t\t\tDELTA I: %f\n",DeltaI);
printf("\n\n\n\t\t\t\t\tALARME DE DELTA I FORA DA BANDA ALVO 5%C \n",37);
printf("t\t\t\t\t****************************************\n");
printf("\t\t\t\t\t");
//for(i=0; i<35; i++) {
//    printf("%c",177); }
printf("\n\n\nt=%.0f",t);
printf("\nZ=%d",z);
printf("\nPot=%.2f",Pot);
printf("\nTmed=%.1f",Tmed);
printf("\nTref=%.1f",Tref);
printf("\nAlvo DeltaI=%f",AlvoDeltaI);
printf("\nDeltaI=%f",DeltaI);
printf("\nDesvioDeltaI=%f",DesvioDeltaI);
printf("\nVariacaoDeltaI=%f",VariacaoDeltaI);
printf("\nPosicao Barra=%d",PosicaoBarra);
printf("\nCboro=%f\n\n\n",Cboro);
// getch(); // Removido para execução automática
//return(0);
   }

   if (DeltaT>1.67 || DeltaT<-1.67) {
printf("\n\n\n\t\t\t\t  TEMPERATURA MEDIA DO SRR: %.1f\n",Tmed);
printf("\n\n\n\t\t\t\tO ALARME DESVIO DE TEMPERATURA 1,67°C\n");
printf("t\t\t\t\t****************************************\n");
printf("\t\t\t\t");
for(i=0; i<37; i++) {
    printf("%c",177); }
printf("\n\n\nt=%.0f",t);
printf("\nZ=%d",z);
printf("\nPot=%.2f",Pot);
printf("\nTmed=%.1f",Tmed);
printf("\nTref=%.1f",Tref);
printf("\nAlvo DeltaI=%f",AlvoDeltaI);
printf("\nDeltaI=%f",DeltaI);
printf("\nDesvioDeltaI=%f",DesvioDeltaI);
printf("\nVariacaoDeltaI=%f",VariacaoDeltaI);
printf("\nPosicao Barra=%d",PosicaoBarra);
printf("\nCboro=%f\n\n\n",Cboro);
// getch(); // Removido para execução automática
//return(0);
   }
 if (Cboro<8) {
printf("\n\n\n\t\t\t\t\tO FIM DO CICLO - PARABENS!!!!!\n");
printf("\t\t\t\t\t");
for(i=0; i<30; i++) {
    printf("%c",177); }
printf("\n\n\nt=%.0f",t);
printf("\nZ=%d",z);
printf("\nPot=%.2f",Pot);
printf("\nTmed=%.1f",Tmed);
printf("\nTref=%.1f",Tref);
printf("\nAlvo DeltaI=%f",AlvoDeltaI);
printf("\nDeltaI=%f",DeltaI);
printf("\nDesvioDeltaI=%f",DesvioDeltaI);
printf("\nVariacaoDeltaI=%f",VariacaoDeltaI);
printf("\nPosicao Barra=%d",PosicaoBarra);
printf("\nCboro=%f\n\n\n",Cboro);
strcpy(termino, "fim"); // Força o fim para o caso de sair por aqui
// getch(); // Removido para execução automática
//return(0);
   }
}
printf ("\n\nFim do Programa\n\n");
// getch(); // Removido para execução automática
return(0);
}



