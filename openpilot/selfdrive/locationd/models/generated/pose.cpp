#include "pose.h"

namespace {
#define DIM 18
#define EDIM 18
#define MEDIM 18
typedef void (*Hfun)(double *, double *, double *);
const static double MAHA_THRESH_4 = 7.814727903251177;
const static double MAHA_THRESH_10 = 7.814727903251177;
const static double MAHA_THRESH_13 = 7.814727903251177;
const static double MAHA_THRESH_14 = 7.814727903251177;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_2178224858840209361) {
   out_2178224858840209361[0] = delta_x[0] + nom_x[0];
   out_2178224858840209361[1] = delta_x[1] + nom_x[1];
   out_2178224858840209361[2] = delta_x[2] + nom_x[2];
   out_2178224858840209361[3] = delta_x[3] + nom_x[3];
   out_2178224858840209361[4] = delta_x[4] + nom_x[4];
   out_2178224858840209361[5] = delta_x[5] + nom_x[5];
   out_2178224858840209361[6] = delta_x[6] + nom_x[6];
   out_2178224858840209361[7] = delta_x[7] + nom_x[7];
   out_2178224858840209361[8] = delta_x[8] + nom_x[8];
   out_2178224858840209361[9] = delta_x[9] + nom_x[9];
   out_2178224858840209361[10] = delta_x[10] + nom_x[10];
   out_2178224858840209361[11] = delta_x[11] + nom_x[11];
   out_2178224858840209361[12] = delta_x[12] + nom_x[12];
   out_2178224858840209361[13] = delta_x[13] + nom_x[13];
   out_2178224858840209361[14] = delta_x[14] + nom_x[14];
   out_2178224858840209361[15] = delta_x[15] + nom_x[15];
   out_2178224858840209361[16] = delta_x[16] + nom_x[16];
   out_2178224858840209361[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_4618004895414237312) {
   out_4618004895414237312[0] = -nom_x[0] + true_x[0];
   out_4618004895414237312[1] = -nom_x[1] + true_x[1];
   out_4618004895414237312[2] = -nom_x[2] + true_x[2];
   out_4618004895414237312[3] = -nom_x[3] + true_x[3];
   out_4618004895414237312[4] = -nom_x[4] + true_x[4];
   out_4618004895414237312[5] = -nom_x[5] + true_x[5];
   out_4618004895414237312[6] = -nom_x[6] + true_x[6];
   out_4618004895414237312[7] = -nom_x[7] + true_x[7];
   out_4618004895414237312[8] = -nom_x[8] + true_x[8];
   out_4618004895414237312[9] = -nom_x[9] + true_x[9];
   out_4618004895414237312[10] = -nom_x[10] + true_x[10];
   out_4618004895414237312[11] = -nom_x[11] + true_x[11];
   out_4618004895414237312[12] = -nom_x[12] + true_x[12];
   out_4618004895414237312[13] = -nom_x[13] + true_x[13];
   out_4618004895414237312[14] = -nom_x[14] + true_x[14];
   out_4618004895414237312[15] = -nom_x[15] + true_x[15];
   out_4618004895414237312[16] = -nom_x[16] + true_x[16];
   out_4618004895414237312[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_6893734767702127169) {
   out_6893734767702127169[0] = 1.0;
   out_6893734767702127169[1] = 0.0;
   out_6893734767702127169[2] = 0.0;
   out_6893734767702127169[3] = 0.0;
   out_6893734767702127169[4] = 0.0;
   out_6893734767702127169[5] = 0.0;
   out_6893734767702127169[6] = 0.0;
   out_6893734767702127169[7] = 0.0;
   out_6893734767702127169[8] = 0.0;
   out_6893734767702127169[9] = 0.0;
   out_6893734767702127169[10] = 0.0;
   out_6893734767702127169[11] = 0.0;
   out_6893734767702127169[12] = 0.0;
   out_6893734767702127169[13] = 0.0;
   out_6893734767702127169[14] = 0.0;
   out_6893734767702127169[15] = 0.0;
   out_6893734767702127169[16] = 0.0;
   out_6893734767702127169[17] = 0.0;
   out_6893734767702127169[18] = 0.0;
   out_6893734767702127169[19] = 1.0;
   out_6893734767702127169[20] = 0.0;
   out_6893734767702127169[21] = 0.0;
   out_6893734767702127169[22] = 0.0;
   out_6893734767702127169[23] = 0.0;
   out_6893734767702127169[24] = 0.0;
   out_6893734767702127169[25] = 0.0;
   out_6893734767702127169[26] = 0.0;
   out_6893734767702127169[27] = 0.0;
   out_6893734767702127169[28] = 0.0;
   out_6893734767702127169[29] = 0.0;
   out_6893734767702127169[30] = 0.0;
   out_6893734767702127169[31] = 0.0;
   out_6893734767702127169[32] = 0.0;
   out_6893734767702127169[33] = 0.0;
   out_6893734767702127169[34] = 0.0;
   out_6893734767702127169[35] = 0.0;
   out_6893734767702127169[36] = 0.0;
   out_6893734767702127169[37] = 0.0;
   out_6893734767702127169[38] = 1.0;
   out_6893734767702127169[39] = 0.0;
   out_6893734767702127169[40] = 0.0;
   out_6893734767702127169[41] = 0.0;
   out_6893734767702127169[42] = 0.0;
   out_6893734767702127169[43] = 0.0;
   out_6893734767702127169[44] = 0.0;
   out_6893734767702127169[45] = 0.0;
   out_6893734767702127169[46] = 0.0;
   out_6893734767702127169[47] = 0.0;
   out_6893734767702127169[48] = 0.0;
   out_6893734767702127169[49] = 0.0;
   out_6893734767702127169[50] = 0.0;
   out_6893734767702127169[51] = 0.0;
   out_6893734767702127169[52] = 0.0;
   out_6893734767702127169[53] = 0.0;
   out_6893734767702127169[54] = 0.0;
   out_6893734767702127169[55] = 0.0;
   out_6893734767702127169[56] = 0.0;
   out_6893734767702127169[57] = 1.0;
   out_6893734767702127169[58] = 0.0;
   out_6893734767702127169[59] = 0.0;
   out_6893734767702127169[60] = 0.0;
   out_6893734767702127169[61] = 0.0;
   out_6893734767702127169[62] = 0.0;
   out_6893734767702127169[63] = 0.0;
   out_6893734767702127169[64] = 0.0;
   out_6893734767702127169[65] = 0.0;
   out_6893734767702127169[66] = 0.0;
   out_6893734767702127169[67] = 0.0;
   out_6893734767702127169[68] = 0.0;
   out_6893734767702127169[69] = 0.0;
   out_6893734767702127169[70] = 0.0;
   out_6893734767702127169[71] = 0.0;
   out_6893734767702127169[72] = 0.0;
   out_6893734767702127169[73] = 0.0;
   out_6893734767702127169[74] = 0.0;
   out_6893734767702127169[75] = 0.0;
   out_6893734767702127169[76] = 1.0;
   out_6893734767702127169[77] = 0.0;
   out_6893734767702127169[78] = 0.0;
   out_6893734767702127169[79] = 0.0;
   out_6893734767702127169[80] = 0.0;
   out_6893734767702127169[81] = 0.0;
   out_6893734767702127169[82] = 0.0;
   out_6893734767702127169[83] = 0.0;
   out_6893734767702127169[84] = 0.0;
   out_6893734767702127169[85] = 0.0;
   out_6893734767702127169[86] = 0.0;
   out_6893734767702127169[87] = 0.0;
   out_6893734767702127169[88] = 0.0;
   out_6893734767702127169[89] = 0.0;
   out_6893734767702127169[90] = 0.0;
   out_6893734767702127169[91] = 0.0;
   out_6893734767702127169[92] = 0.0;
   out_6893734767702127169[93] = 0.0;
   out_6893734767702127169[94] = 0.0;
   out_6893734767702127169[95] = 1.0;
   out_6893734767702127169[96] = 0.0;
   out_6893734767702127169[97] = 0.0;
   out_6893734767702127169[98] = 0.0;
   out_6893734767702127169[99] = 0.0;
   out_6893734767702127169[100] = 0.0;
   out_6893734767702127169[101] = 0.0;
   out_6893734767702127169[102] = 0.0;
   out_6893734767702127169[103] = 0.0;
   out_6893734767702127169[104] = 0.0;
   out_6893734767702127169[105] = 0.0;
   out_6893734767702127169[106] = 0.0;
   out_6893734767702127169[107] = 0.0;
   out_6893734767702127169[108] = 0.0;
   out_6893734767702127169[109] = 0.0;
   out_6893734767702127169[110] = 0.0;
   out_6893734767702127169[111] = 0.0;
   out_6893734767702127169[112] = 0.0;
   out_6893734767702127169[113] = 0.0;
   out_6893734767702127169[114] = 1.0;
   out_6893734767702127169[115] = 0.0;
   out_6893734767702127169[116] = 0.0;
   out_6893734767702127169[117] = 0.0;
   out_6893734767702127169[118] = 0.0;
   out_6893734767702127169[119] = 0.0;
   out_6893734767702127169[120] = 0.0;
   out_6893734767702127169[121] = 0.0;
   out_6893734767702127169[122] = 0.0;
   out_6893734767702127169[123] = 0.0;
   out_6893734767702127169[124] = 0.0;
   out_6893734767702127169[125] = 0.0;
   out_6893734767702127169[126] = 0.0;
   out_6893734767702127169[127] = 0.0;
   out_6893734767702127169[128] = 0.0;
   out_6893734767702127169[129] = 0.0;
   out_6893734767702127169[130] = 0.0;
   out_6893734767702127169[131] = 0.0;
   out_6893734767702127169[132] = 0.0;
   out_6893734767702127169[133] = 1.0;
   out_6893734767702127169[134] = 0.0;
   out_6893734767702127169[135] = 0.0;
   out_6893734767702127169[136] = 0.0;
   out_6893734767702127169[137] = 0.0;
   out_6893734767702127169[138] = 0.0;
   out_6893734767702127169[139] = 0.0;
   out_6893734767702127169[140] = 0.0;
   out_6893734767702127169[141] = 0.0;
   out_6893734767702127169[142] = 0.0;
   out_6893734767702127169[143] = 0.0;
   out_6893734767702127169[144] = 0.0;
   out_6893734767702127169[145] = 0.0;
   out_6893734767702127169[146] = 0.0;
   out_6893734767702127169[147] = 0.0;
   out_6893734767702127169[148] = 0.0;
   out_6893734767702127169[149] = 0.0;
   out_6893734767702127169[150] = 0.0;
   out_6893734767702127169[151] = 0.0;
   out_6893734767702127169[152] = 1.0;
   out_6893734767702127169[153] = 0.0;
   out_6893734767702127169[154] = 0.0;
   out_6893734767702127169[155] = 0.0;
   out_6893734767702127169[156] = 0.0;
   out_6893734767702127169[157] = 0.0;
   out_6893734767702127169[158] = 0.0;
   out_6893734767702127169[159] = 0.0;
   out_6893734767702127169[160] = 0.0;
   out_6893734767702127169[161] = 0.0;
   out_6893734767702127169[162] = 0.0;
   out_6893734767702127169[163] = 0.0;
   out_6893734767702127169[164] = 0.0;
   out_6893734767702127169[165] = 0.0;
   out_6893734767702127169[166] = 0.0;
   out_6893734767702127169[167] = 0.0;
   out_6893734767702127169[168] = 0.0;
   out_6893734767702127169[169] = 0.0;
   out_6893734767702127169[170] = 0.0;
   out_6893734767702127169[171] = 1.0;
   out_6893734767702127169[172] = 0.0;
   out_6893734767702127169[173] = 0.0;
   out_6893734767702127169[174] = 0.0;
   out_6893734767702127169[175] = 0.0;
   out_6893734767702127169[176] = 0.0;
   out_6893734767702127169[177] = 0.0;
   out_6893734767702127169[178] = 0.0;
   out_6893734767702127169[179] = 0.0;
   out_6893734767702127169[180] = 0.0;
   out_6893734767702127169[181] = 0.0;
   out_6893734767702127169[182] = 0.0;
   out_6893734767702127169[183] = 0.0;
   out_6893734767702127169[184] = 0.0;
   out_6893734767702127169[185] = 0.0;
   out_6893734767702127169[186] = 0.0;
   out_6893734767702127169[187] = 0.0;
   out_6893734767702127169[188] = 0.0;
   out_6893734767702127169[189] = 0.0;
   out_6893734767702127169[190] = 1.0;
   out_6893734767702127169[191] = 0.0;
   out_6893734767702127169[192] = 0.0;
   out_6893734767702127169[193] = 0.0;
   out_6893734767702127169[194] = 0.0;
   out_6893734767702127169[195] = 0.0;
   out_6893734767702127169[196] = 0.0;
   out_6893734767702127169[197] = 0.0;
   out_6893734767702127169[198] = 0.0;
   out_6893734767702127169[199] = 0.0;
   out_6893734767702127169[200] = 0.0;
   out_6893734767702127169[201] = 0.0;
   out_6893734767702127169[202] = 0.0;
   out_6893734767702127169[203] = 0.0;
   out_6893734767702127169[204] = 0.0;
   out_6893734767702127169[205] = 0.0;
   out_6893734767702127169[206] = 0.0;
   out_6893734767702127169[207] = 0.0;
   out_6893734767702127169[208] = 0.0;
   out_6893734767702127169[209] = 1.0;
   out_6893734767702127169[210] = 0.0;
   out_6893734767702127169[211] = 0.0;
   out_6893734767702127169[212] = 0.0;
   out_6893734767702127169[213] = 0.0;
   out_6893734767702127169[214] = 0.0;
   out_6893734767702127169[215] = 0.0;
   out_6893734767702127169[216] = 0.0;
   out_6893734767702127169[217] = 0.0;
   out_6893734767702127169[218] = 0.0;
   out_6893734767702127169[219] = 0.0;
   out_6893734767702127169[220] = 0.0;
   out_6893734767702127169[221] = 0.0;
   out_6893734767702127169[222] = 0.0;
   out_6893734767702127169[223] = 0.0;
   out_6893734767702127169[224] = 0.0;
   out_6893734767702127169[225] = 0.0;
   out_6893734767702127169[226] = 0.0;
   out_6893734767702127169[227] = 0.0;
   out_6893734767702127169[228] = 1.0;
   out_6893734767702127169[229] = 0.0;
   out_6893734767702127169[230] = 0.0;
   out_6893734767702127169[231] = 0.0;
   out_6893734767702127169[232] = 0.0;
   out_6893734767702127169[233] = 0.0;
   out_6893734767702127169[234] = 0.0;
   out_6893734767702127169[235] = 0.0;
   out_6893734767702127169[236] = 0.0;
   out_6893734767702127169[237] = 0.0;
   out_6893734767702127169[238] = 0.0;
   out_6893734767702127169[239] = 0.0;
   out_6893734767702127169[240] = 0.0;
   out_6893734767702127169[241] = 0.0;
   out_6893734767702127169[242] = 0.0;
   out_6893734767702127169[243] = 0.0;
   out_6893734767702127169[244] = 0.0;
   out_6893734767702127169[245] = 0.0;
   out_6893734767702127169[246] = 0.0;
   out_6893734767702127169[247] = 1.0;
   out_6893734767702127169[248] = 0.0;
   out_6893734767702127169[249] = 0.0;
   out_6893734767702127169[250] = 0.0;
   out_6893734767702127169[251] = 0.0;
   out_6893734767702127169[252] = 0.0;
   out_6893734767702127169[253] = 0.0;
   out_6893734767702127169[254] = 0.0;
   out_6893734767702127169[255] = 0.0;
   out_6893734767702127169[256] = 0.0;
   out_6893734767702127169[257] = 0.0;
   out_6893734767702127169[258] = 0.0;
   out_6893734767702127169[259] = 0.0;
   out_6893734767702127169[260] = 0.0;
   out_6893734767702127169[261] = 0.0;
   out_6893734767702127169[262] = 0.0;
   out_6893734767702127169[263] = 0.0;
   out_6893734767702127169[264] = 0.0;
   out_6893734767702127169[265] = 0.0;
   out_6893734767702127169[266] = 1.0;
   out_6893734767702127169[267] = 0.0;
   out_6893734767702127169[268] = 0.0;
   out_6893734767702127169[269] = 0.0;
   out_6893734767702127169[270] = 0.0;
   out_6893734767702127169[271] = 0.0;
   out_6893734767702127169[272] = 0.0;
   out_6893734767702127169[273] = 0.0;
   out_6893734767702127169[274] = 0.0;
   out_6893734767702127169[275] = 0.0;
   out_6893734767702127169[276] = 0.0;
   out_6893734767702127169[277] = 0.0;
   out_6893734767702127169[278] = 0.0;
   out_6893734767702127169[279] = 0.0;
   out_6893734767702127169[280] = 0.0;
   out_6893734767702127169[281] = 0.0;
   out_6893734767702127169[282] = 0.0;
   out_6893734767702127169[283] = 0.0;
   out_6893734767702127169[284] = 0.0;
   out_6893734767702127169[285] = 1.0;
   out_6893734767702127169[286] = 0.0;
   out_6893734767702127169[287] = 0.0;
   out_6893734767702127169[288] = 0.0;
   out_6893734767702127169[289] = 0.0;
   out_6893734767702127169[290] = 0.0;
   out_6893734767702127169[291] = 0.0;
   out_6893734767702127169[292] = 0.0;
   out_6893734767702127169[293] = 0.0;
   out_6893734767702127169[294] = 0.0;
   out_6893734767702127169[295] = 0.0;
   out_6893734767702127169[296] = 0.0;
   out_6893734767702127169[297] = 0.0;
   out_6893734767702127169[298] = 0.0;
   out_6893734767702127169[299] = 0.0;
   out_6893734767702127169[300] = 0.0;
   out_6893734767702127169[301] = 0.0;
   out_6893734767702127169[302] = 0.0;
   out_6893734767702127169[303] = 0.0;
   out_6893734767702127169[304] = 1.0;
   out_6893734767702127169[305] = 0.0;
   out_6893734767702127169[306] = 0.0;
   out_6893734767702127169[307] = 0.0;
   out_6893734767702127169[308] = 0.0;
   out_6893734767702127169[309] = 0.0;
   out_6893734767702127169[310] = 0.0;
   out_6893734767702127169[311] = 0.0;
   out_6893734767702127169[312] = 0.0;
   out_6893734767702127169[313] = 0.0;
   out_6893734767702127169[314] = 0.0;
   out_6893734767702127169[315] = 0.0;
   out_6893734767702127169[316] = 0.0;
   out_6893734767702127169[317] = 0.0;
   out_6893734767702127169[318] = 0.0;
   out_6893734767702127169[319] = 0.0;
   out_6893734767702127169[320] = 0.0;
   out_6893734767702127169[321] = 0.0;
   out_6893734767702127169[322] = 0.0;
   out_6893734767702127169[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_6153064126878909392) {
   out_6153064126878909392[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_6153064126878909392[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_6153064126878909392[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_6153064126878909392[3] = dt*state[12] + state[3];
   out_6153064126878909392[4] = dt*state[13] + state[4];
   out_6153064126878909392[5] = dt*state[14] + state[5];
   out_6153064126878909392[6] = state[6];
   out_6153064126878909392[7] = state[7];
   out_6153064126878909392[8] = state[8];
   out_6153064126878909392[9] = state[9];
   out_6153064126878909392[10] = state[10];
   out_6153064126878909392[11] = state[11];
   out_6153064126878909392[12] = state[12];
   out_6153064126878909392[13] = state[13];
   out_6153064126878909392[14] = state[14];
   out_6153064126878909392[15] = state[15];
   out_6153064126878909392[16] = state[16];
   out_6153064126878909392[17] = state[17];
}
void F_fun(double *state, double dt, double *out_3286506466705227237) {
   out_3286506466705227237[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3286506466705227237[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3286506466705227237[2] = 0;
   out_3286506466705227237[3] = 0;
   out_3286506466705227237[4] = 0;
   out_3286506466705227237[5] = 0;
   out_3286506466705227237[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3286506466705227237[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3286506466705227237[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3286506466705227237[9] = 0;
   out_3286506466705227237[10] = 0;
   out_3286506466705227237[11] = 0;
   out_3286506466705227237[12] = 0;
   out_3286506466705227237[13] = 0;
   out_3286506466705227237[14] = 0;
   out_3286506466705227237[15] = 0;
   out_3286506466705227237[16] = 0;
   out_3286506466705227237[17] = 0;
   out_3286506466705227237[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3286506466705227237[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3286506466705227237[20] = 0;
   out_3286506466705227237[21] = 0;
   out_3286506466705227237[22] = 0;
   out_3286506466705227237[23] = 0;
   out_3286506466705227237[24] = 0;
   out_3286506466705227237[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3286506466705227237[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3286506466705227237[27] = 0;
   out_3286506466705227237[28] = 0;
   out_3286506466705227237[29] = 0;
   out_3286506466705227237[30] = 0;
   out_3286506466705227237[31] = 0;
   out_3286506466705227237[32] = 0;
   out_3286506466705227237[33] = 0;
   out_3286506466705227237[34] = 0;
   out_3286506466705227237[35] = 0;
   out_3286506466705227237[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3286506466705227237[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3286506466705227237[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3286506466705227237[39] = 0;
   out_3286506466705227237[40] = 0;
   out_3286506466705227237[41] = 0;
   out_3286506466705227237[42] = 0;
   out_3286506466705227237[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3286506466705227237[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3286506466705227237[45] = 0;
   out_3286506466705227237[46] = 0;
   out_3286506466705227237[47] = 0;
   out_3286506466705227237[48] = 0;
   out_3286506466705227237[49] = 0;
   out_3286506466705227237[50] = 0;
   out_3286506466705227237[51] = 0;
   out_3286506466705227237[52] = 0;
   out_3286506466705227237[53] = 0;
   out_3286506466705227237[54] = 0;
   out_3286506466705227237[55] = 0;
   out_3286506466705227237[56] = 0;
   out_3286506466705227237[57] = 1;
   out_3286506466705227237[58] = 0;
   out_3286506466705227237[59] = 0;
   out_3286506466705227237[60] = 0;
   out_3286506466705227237[61] = 0;
   out_3286506466705227237[62] = 0;
   out_3286506466705227237[63] = 0;
   out_3286506466705227237[64] = 0;
   out_3286506466705227237[65] = 0;
   out_3286506466705227237[66] = dt;
   out_3286506466705227237[67] = 0;
   out_3286506466705227237[68] = 0;
   out_3286506466705227237[69] = 0;
   out_3286506466705227237[70] = 0;
   out_3286506466705227237[71] = 0;
   out_3286506466705227237[72] = 0;
   out_3286506466705227237[73] = 0;
   out_3286506466705227237[74] = 0;
   out_3286506466705227237[75] = 0;
   out_3286506466705227237[76] = 1;
   out_3286506466705227237[77] = 0;
   out_3286506466705227237[78] = 0;
   out_3286506466705227237[79] = 0;
   out_3286506466705227237[80] = 0;
   out_3286506466705227237[81] = 0;
   out_3286506466705227237[82] = 0;
   out_3286506466705227237[83] = 0;
   out_3286506466705227237[84] = 0;
   out_3286506466705227237[85] = dt;
   out_3286506466705227237[86] = 0;
   out_3286506466705227237[87] = 0;
   out_3286506466705227237[88] = 0;
   out_3286506466705227237[89] = 0;
   out_3286506466705227237[90] = 0;
   out_3286506466705227237[91] = 0;
   out_3286506466705227237[92] = 0;
   out_3286506466705227237[93] = 0;
   out_3286506466705227237[94] = 0;
   out_3286506466705227237[95] = 1;
   out_3286506466705227237[96] = 0;
   out_3286506466705227237[97] = 0;
   out_3286506466705227237[98] = 0;
   out_3286506466705227237[99] = 0;
   out_3286506466705227237[100] = 0;
   out_3286506466705227237[101] = 0;
   out_3286506466705227237[102] = 0;
   out_3286506466705227237[103] = 0;
   out_3286506466705227237[104] = dt;
   out_3286506466705227237[105] = 0;
   out_3286506466705227237[106] = 0;
   out_3286506466705227237[107] = 0;
   out_3286506466705227237[108] = 0;
   out_3286506466705227237[109] = 0;
   out_3286506466705227237[110] = 0;
   out_3286506466705227237[111] = 0;
   out_3286506466705227237[112] = 0;
   out_3286506466705227237[113] = 0;
   out_3286506466705227237[114] = 1;
   out_3286506466705227237[115] = 0;
   out_3286506466705227237[116] = 0;
   out_3286506466705227237[117] = 0;
   out_3286506466705227237[118] = 0;
   out_3286506466705227237[119] = 0;
   out_3286506466705227237[120] = 0;
   out_3286506466705227237[121] = 0;
   out_3286506466705227237[122] = 0;
   out_3286506466705227237[123] = 0;
   out_3286506466705227237[124] = 0;
   out_3286506466705227237[125] = 0;
   out_3286506466705227237[126] = 0;
   out_3286506466705227237[127] = 0;
   out_3286506466705227237[128] = 0;
   out_3286506466705227237[129] = 0;
   out_3286506466705227237[130] = 0;
   out_3286506466705227237[131] = 0;
   out_3286506466705227237[132] = 0;
   out_3286506466705227237[133] = 1;
   out_3286506466705227237[134] = 0;
   out_3286506466705227237[135] = 0;
   out_3286506466705227237[136] = 0;
   out_3286506466705227237[137] = 0;
   out_3286506466705227237[138] = 0;
   out_3286506466705227237[139] = 0;
   out_3286506466705227237[140] = 0;
   out_3286506466705227237[141] = 0;
   out_3286506466705227237[142] = 0;
   out_3286506466705227237[143] = 0;
   out_3286506466705227237[144] = 0;
   out_3286506466705227237[145] = 0;
   out_3286506466705227237[146] = 0;
   out_3286506466705227237[147] = 0;
   out_3286506466705227237[148] = 0;
   out_3286506466705227237[149] = 0;
   out_3286506466705227237[150] = 0;
   out_3286506466705227237[151] = 0;
   out_3286506466705227237[152] = 1;
   out_3286506466705227237[153] = 0;
   out_3286506466705227237[154] = 0;
   out_3286506466705227237[155] = 0;
   out_3286506466705227237[156] = 0;
   out_3286506466705227237[157] = 0;
   out_3286506466705227237[158] = 0;
   out_3286506466705227237[159] = 0;
   out_3286506466705227237[160] = 0;
   out_3286506466705227237[161] = 0;
   out_3286506466705227237[162] = 0;
   out_3286506466705227237[163] = 0;
   out_3286506466705227237[164] = 0;
   out_3286506466705227237[165] = 0;
   out_3286506466705227237[166] = 0;
   out_3286506466705227237[167] = 0;
   out_3286506466705227237[168] = 0;
   out_3286506466705227237[169] = 0;
   out_3286506466705227237[170] = 0;
   out_3286506466705227237[171] = 1;
   out_3286506466705227237[172] = 0;
   out_3286506466705227237[173] = 0;
   out_3286506466705227237[174] = 0;
   out_3286506466705227237[175] = 0;
   out_3286506466705227237[176] = 0;
   out_3286506466705227237[177] = 0;
   out_3286506466705227237[178] = 0;
   out_3286506466705227237[179] = 0;
   out_3286506466705227237[180] = 0;
   out_3286506466705227237[181] = 0;
   out_3286506466705227237[182] = 0;
   out_3286506466705227237[183] = 0;
   out_3286506466705227237[184] = 0;
   out_3286506466705227237[185] = 0;
   out_3286506466705227237[186] = 0;
   out_3286506466705227237[187] = 0;
   out_3286506466705227237[188] = 0;
   out_3286506466705227237[189] = 0;
   out_3286506466705227237[190] = 1;
   out_3286506466705227237[191] = 0;
   out_3286506466705227237[192] = 0;
   out_3286506466705227237[193] = 0;
   out_3286506466705227237[194] = 0;
   out_3286506466705227237[195] = 0;
   out_3286506466705227237[196] = 0;
   out_3286506466705227237[197] = 0;
   out_3286506466705227237[198] = 0;
   out_3286506466705227237[199] = 0;
   out_3286506466705227237[200] = 0;
   out_3286506466705227237[201] = 0;
   out_3286506466705227237[202] = 0;
   out_3286506466705227237[203] = 0;
   out_3286506466705227237[204] = 0;
   out_3286506466705227237[205] = 0;
   out_3286506466705227237[206] = 0;
   out_3286506466705227237[207] = 0;
   out_3286506466705227237[208] = 0;
   out_3286506466705227237[209] = 1;
   out_3286506466705227237[210] = 0;
   out_3286506466705227237[211] = 0;
   out_3286506466705227237[212] = 0;
   out_3286506466705227237[213] = 0;
   out_3286506466705227237[214] = 0;
   out_3286506466705227237[215] = 0;
   out_3286506466705227237[216] = 0;
   out_3286506466705227237[217] = 0;
   out_3286506466705227237[218] = 0;
   out_3286506466705227237[219] = 0;
   out_3286506466705227237[220] = 0;
   out_3286506466705227237[221] = 0;
   out_3286506466705227237[222] = 0;
   out_3286506466705227237[223] = 0;
   out_3286506466705227237[224] = 0;
   out_3286506466705227237[225] = 0;
   out_3286506466705227237[226] = 0;
   out_3286506466705227237[227] = 0;
   out_3286506466705227237[228] = 1;
   out_3286506466705227237[229] = 0;
   out_3286506466705227237[230] = 0;
   out_3286506466705227237[231] = 0;
   out_3286506466705227237[232] = 0;
   out_3286506466705227237[233] = 0;
   out_3286506466705227237[234] = 0;
   out_3286506466705227237[235] = 0;
   out_3286506466705227237[236] = 0;
   out_3286506466705227237[237] = 0;
   out_3286506466705227237[238] = 0;
   out_3286506466705227237[239] = 0;
   out_3286506466705227237[240] = 0;
   out_3286506466705227237[241] = 0;
   out_3286506466705227237[242] = 0;
   out_3286506466705227237[243] = 0;
   out_3286506466705227237[244] = 0;
   out_3286506466705227237[245] = 0;
   out_3286506466705227237[246] = 0;
   out_3286506466705227237[247] = 1;
   out_3286506466705227237[248] = 0;
   out_3286506466705227237[249] = 0;
   out_3286506466705227237[250] = 0;
   out_3286506466705227237[251] = 0;
   out_3286506466705227237[252] = 0;
   out_3286506466705227237[253] = 0;
   out_3286506466705227237[254] = 0;
   out_3286506466705227237[255] = 0;
   out_3286506466705227237[256] = 0;
   out_3286506466705227237[257] = 0;
   out_3286506466705227237[258] = 0;
   out_3286506466705227237[259] = 0;
   out_3286506466705227237[260] = 0;
   out_3286506466705227237[261] = 0;
   out_3286506466705227237[262] = 0;
   out_3286506466705227237[263] = 0;
   out_3286506466705227237[264] = 0;
   out_3286506466705227237[265] = 0;
   out_3286506466705227237[266] = 1;
   out_3286506466705227237[267] = 0;
   out_3286506466705227237[268] = 0;
   out_3286506466705227237[269] = 0;
   out_3286506466705227237[270] = 0;
   out_3286506466705227237[271] = 0;
   out_3286506466705227237[272] = 0;
   out_3286506466705227237[273] = 0;
   out_3286506466705227237[274] = 0;
   out_3286506466705227237[275] = 0;
   out_3286506466705227237[276] = 0;
   out_3286506466705227237[277] = 0;
   out_3286506466705227237[278] = 0;
   out_3286506466705227237[279] = 0;
   out_3286506466705227237[280] = 0;
   out_3286506466705227237[281] = 0;
   out_3286506466705227237[282] = 0;
   out_3286506466705227237[283] = 0;
   out_3286506466705227237[284] = 0;
   out_3286506466705227237[285] = 1;
   out_3286506466705227237[286] = 0;
   out_3286506466705227237[287] = 0;
   out_3286506466705227237[288] = 0;
   out_3286506466705227237[289] = 0;
   out_3286506466705227237[290] = 0;
   out_3286506466705227237[291] = 0;
   out_3286506466705227237[292] = 0;
   out_3286506466705227237[293] = 0;
   out_3286506466705227237[294] = 0;
   out_3286506466705227237[295] = 0;
   out_3286506466705227237[296] = 0;
   out_3286506466705227237[297] = 0;
   out_3286506466705227237[298] = 0;
   out_3286506466705227237[299] = 0;
   out_3286506466705227237[300] = 0;
   out_3286506466705227237[301] = 0;
   out_3286506466705227237[302] = 0;
   out_3286506466705227237[303] = 0;
   out_3286506466705227237[304] = 1;
   out_3286506466705227237[305] = 0;
   out_3286506466705227237[306] = 0;
   out_3286506466705227237[307] = 0;
   out_3286506466705227237[308] = 0;
   out_3286506466705227237[309] = 0;
   out_3286506466705227237[310] = 0;
   out_3286506466705227237[311] = 0;
   out_3286506466705227237[312] = 0;
   out_3286506466705227237[313] = 0;
   out_3286506466705227237[314] = 0;
   out_3286506466705227237[315] = 0;
   out_3286506466705227237[316] = 0;
   out_3286506466705227237[317] = 0;
   out_3286506466705227237[318] = 0;
   out_3286506466705227237[319] = 0;
   out_3286506466705227237[320] = 0;
   out_3286506466705227237[321] = 0;
   out_3286506466705227237[322] = 0;
   out_3286506466705227237[323] = 1;
}
void h_4(double *state, double *unused, double *out_3648588459832896841) {
   out_3648588459832896841[0] = state[6] + state[9];
   out_3648588459832896841[1] = state[7] + state[10];
   out_3648588459832896841[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_5695787285819229065) {
   out_5695787285819229065[0] = 0;
   out_5695787285819229065[1] = 0;
   out_5695787285819229065[2] = 0;
   out_5695787285819229065[3] = 0;
   out_5695787285819229065[4] = 0;
   out_5695787285819229065[5] = 0;
   out_5695787285819229065[6] = 1;
   out_5695787285819229065[7] = 0;
   out_5695787285819229065[8] = 0;
   out_5695787285819229065[9] = 1;
   out_5695787285819229065[10] = 0;
   out_5695787285819229065[11] = 0;
   out_5695787285819229065[12] = 0;
   out_5695787285819229065[13] = 0;
   out_5695787285819229065[14] = 0;
   out_5695787285819229065[15] = 0;
   out_5695787285819229065[16] = 0;
   out_5695787285819229065[17] = 0;
   out_5695787285819229065[18] = 0;
   out_5695787285819229065[19] = 0;
   out_5695787285819229065[20] = 0;
   out_5695787285819229065[21] = 0;
   out_5695787285819229065[22] = 0;
   out_5695787285819229065[23] = 0;
   out_5695787285819229065[24] = 0;
   out_5695787285819229065[25] = 1;
   out_5695787285819229065[26] = 0;
   out_5695787285819229065[27] = 0;
   out_5695787285819229065[28] = 1;
   out_5695787285819229065[29] = 0;
   out_5695787285819229065[30] = 0;
   out_5695787285819229065[31] = 0;
   out_5695787285819229065[32] = 0;
   out_5695787285819229065[33] = 0;
   out_5695787285819229065[34] = 0;
   out_5695787285819229065[35] = 0;
   out_5695787285819229065[36] = 0;
   out_5695787285819229065[37] = 0;
   out_5695787285819229065[38] = 0;
   out_5695787285819229065[39] = 0;
   out_5695787285819229065[40] = 0;
   out_5695787285819229065[41] = 0;
   out_5695787285819229065[42] = 0;
   out_5695787285819229065[43] = 0;
   out_5695787285819229065[44] = 1;
   out_5695787285819229065[45] = 0;
   out_5695787285819229065[46] = 0;
   out_5695787285819229065[47] = 1;
   out_5695787285819229065[48] = 0;
   out_5695787285819229065[49] = 0;
   out_5695787285819229065[50] = 0;
   out_5695787285819229065[51] = 0;
   out_5695787285819229065[52] = 0;
   out_5695787285819229065[53] = 0;
}
void h_10(double *state, double *unused, double *out_7983794647515202819) {
   out_7983794647515202819[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_7983794647515202819[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_7983794647515202819[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_3032931921094903591) {
   out_3032931921094903591[0] = 0;
   out_3032931921094903591[1] = 9.8100000000000005*cos(state[1]);
   out_3032931921094903591[2] = 0;
   out_3032931921094903591[3] = 0;
   out_3032931921094903591[4] = -state[8];
   out_3032931921094903591[5] = state[7];
   out_3032931921094903591[6] = 0;
   out_3032931921094903591[7] = state[5];
   out_3032931921094903591[8] = -state[4];
   out_3032931921094903591[9] = 0;
   out_3032931921094903591[10] = 0;
   out_3032931921094903591[11] = 0;
   out_3032931921094903591[12] = 1;
   out_3032931921094903591[13] = 0;
   out_3032931921094903591[14] = 0;
   out_3032931921094903591[15] = 1;
   out_3032931921094903591[16] = 0;
   out_3032931921094903591[17] = 0;
   out_3032931921094903591[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_3032931921094903591[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_3032931921094903591[20] = 0;
   out_3032931921094903591[21] = state[8];
   out_3032931921094903591[22] = 0;
   out_3032931921094903591[23] = -state[6];
   out_3032931921094903591[24] = -state[5];
   out_3032931921094903591[25] = 0;
   out_3032931921094903591[26] = state[3];
   out_3032931921094903591[27] = 0;
   out_3032931921094903591[28] = 0;
   out_3032931921094903591[29] = 0;
   out_3032931921094903591[30] = 0;
   out_3032931921094903591[31] = 1;
   out_3032931921094903591[32] = 0;
   out_3032931921094903591[33] = 0;
   out_3032931921094903591[34] = 1;
   out_3032931921094903591[35] = 0;
   out_3032931921094903591[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_3032931921094903591[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_3032931921094903591[38] = 0;
   out_3032931921094903591[39] = -state[7];
   out_3032931921094903591[40] = state[6];
   out_3032931921094903591[41] = 0;
   out_3032931921094903591[42] = state[4];
   out_3032931921094903591[43] = -state[3];
   out_3032931921094903591[44] = 0;
   out_3032931921094903591[45] = 0;
   out_3032931921094903591[46] = 0;
   out_3032931921094903591[47] = 0;
   out_3032931921094903591[48] = 0;
   out_3032931921094903591[49] = 0;
   out_3032931921094903591[50] = 1;
   out_3032931921094903591[51] = 0;
   out_3032931921094903591[52] = 0;
   out_3032931921094903591[53] = 1;
}
void h_13(double *state, double *unused, double *out_1190906095138799015) {
   out_1190906095138799015[0] = state[3];
   out_1190906095138799015[1] = state[4];
   out_1190906095138799015[2] = state[5];
}
void H_13(double *state, double *unused, double *out_2483513460486896264) {
   out_2483513460486896264[0] = 0;
   out_2483513460486896264[1] = 0;
   out_2483513460486896264[2] = 0;
   out_2483513460486896264[3] = 1;
   out_2483513460486896264[4] = 0;
   out_2483513460486896264[5] = 0;
   out_2483513460486896264[6] = 0;
   out_2483513460486896264[7] = 0;
   out_2483513460486896264[8] = 0;
   out_2483513460486896264[9] = 0;
   out_2483513460486896264[10] = 0;
   out_2483513460486896264[11] = 0;
   out_2483513460486896264[12] = 0;
   out_2483513460486896264[13] = 0;
   out_2483513460486896264[14] = 0;
   out_2483513460486896264[15] = 0;
   out_2483513460486896264[16] = 0;
   out_2483513460486896264[17] = 0;
   out_2483513460486896264[18] = 0;
   out_2483513460486896264[19] = 0;
   out_2483513460486896264[20] = 0;
   out_2483513460486896264[21] = 0;
   out_2483513460486896264[22] = 1;
   out_2483513460486896264[23] = 0;
   out_2483513460486896264[24] = 0;
   out_2483513460486896264[25] = 0;
   out_2483513460486896264[26] = 0;
   out_2483513460486896264[27] = 0;
   out_2483513460486896264[28] = 0;
   out_2483513460486896264[29] = 0;
   out_2483513460486896264[30] = 0;
   out_2483513460486896264[31] = 0;
   out_2483513460486896264[32] = 0;
   out_2483513460486896264[33] = 0;
   out_2483513460486896264[34] = 0;
   out_2483513460486896264[35] = 0;
   out_2483513460486896264[36] = 0;
   out_2483513460486896264[37] = 0;
   out_2483513460486896264[38] = 0;
   out_2483513460486896264[39] = 0;
   out_2483513460486896264[40] = 0;
   out_2483513460486896264[41] = 1;
   out_2483513460486896264[42] = 0;
   out_2483513460486896264[43] = 0;
   out_2483513460486896264[44] = 0;
   out_2483513460486896264[45] = 0;
   out_2483513460486896264[46] = 0;
   out_2483513460486896264[47] = 0;
   out_2483513460486896264[48] = 0;
   out_2483513460486896264[49] = 0;
   out_2483513460486896264[50] = 0;
   out_2483513460486896264[51] = 0;
   out_2483513460486896264[52] = 0;
   out_2483513460486896264[53] = 0;
}
void h_14(double *state, double *unused, double *out_4979926043979174598) {
   out_4979926043979174598[0] = state[6];
   out_4979926043979174598[1] = state[7];
   out_4979926043979174598[2] = state[8];
}
void H_14(double *state, double *unused, double *out_8778575718114601361) {
   out_8778575718114601361[0] = 0;
   out_8778575718114601361[1] = 0;
   out_8778575718114601361[2] = 0;
   out_8778575718114601361[3] = 0;
   out_8778575718114601361[4] = 0;
   out_8778575718114601361[5] = 0;
   out_8778575718114601361[6] = 1;
   out_8778575718114601361[7] = 0;
   out_8778575718114601361[8] = 0;
   out_8778575718114601361[9] = 0;
   out_8778575718114601361[10] = 0;
   out_8778575718114601361[11] = 0;
   out_8778575718114601361[12] = 0;
   out_8778575718114601361[13] = 0;
   out_8778575718114601361[14] = 0;
   out_8778575718114601361[15] = 0;
   out_8778575718114601361[16] = 0;
   out_8778575718114601361[17] = 0;
   out_8778575718114601361[18] = 0;
   out_8778575718114601361[19] = 0;
   out_8778575718114601361[20] = 0;
   out_8778575718114601361[21] = 0;
   out_8778575718114601361[22] = 0;
   out_8778575718114601361[23] = 0;
   out_8778575718114601361[24] = 0;
   out_8778575718114601361[25] = 1;
   out_8778575718114601361[26] = 0;
   out_8778575718114601361[27] = 0;
   out_8778575718114601361[28] = 0;
   out_8778575718114601361[29] = 0;
   out_8778575718114601361[30] = 0;
   out_8778575718114601361[31] = 0;
   out_8778575718114601361[32] = 0;
   out_8778575718114601361[33] = 0;
   out_8778575718114601361[34] = 0;
   out_8778575718114601361[35] = 0;
   out_8778575718114601361[36] = 0;
   out_8778575718114601361[37] = 0;
   out_8778575718114601361[38] = 0;
   out_8778575718114601361[39] = 0;
   out_8778575718114601361[40] = 0;
   out_8778575718114601361[41] = 0;
   out_8778575718114601361[42] = 0;
   out_8778575718114601361[43] = 0;
   out_8778575718114601361[44] = 1;
   out_8778575718114601361[45] = 0;
   out_8778575718114601361[46] = 0;
   out_8778575718114601361[47] = 0;
   out_8778575718114601361[48] = 0;
   out_8778575718114601361[49] = 0;
   out_8778575718114601361[50] = 0;
   out_8778575718114601361[51] = 0;
   out_8778575718114601361[52] = 0;
   out_8778575718114601361[53] = 0;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_4, H_4, NULL, in_z, in_R, in_ea, MAHA_THRESH_4);
}
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_10, H_10, NULL, in_z, in_R, in_ea, MAHA_THRESH_10);
}
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_13, H_13, NULL, in_z, in_R, in_ea, MAHA_THRESH_13);
}
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_14, H_14, NULL, in_z, in_R, in_ea, MAHA_THRESH_14);
}
void pose_err_fun(double *nom_x, double *delta_x, double *out_2178224858840209361) {
  err_fun(nom_x, delta_x, out_2178224858840209361);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_4618004895414237312) {
  inv_err_fun(nom_x, true_x, out_4618004895414237312);
}
void pose_H_mod_fun(double *state, double *out_6893734767702127169) {
  H_mod_fun(state, out_6893734767702127169);
}
void pose_f_fun(double *state, double dt, double *out_6153064126878909392) {
  f_fun(state,  dt, out_6153064126878909392);
}
void pose_F_fun(double *state, double dt, double *out_3286506466705227237) {
  F_fun(state,  dt, out_3286506466705227237);
}
void pose_h_4(double *state, double *unused, double *out_3648588459832896841) {
  h_4(state, unused, out_3648588459832896841);
}
void pose_H_4(double *state, double *unused, double *out_5695787285819229065) {
  H_4(state, unused, out_5695787285819229065);
}
void pose_h_10(double *state, double *unused, double *out_7983794647515202819) {
  h_10(state, unused, out_7983794647515202819);
}
void pose_H_10(double *state, double *unused, double *out_3032931921094903591) {
  H_10(state, unused, out_3032931921094903591);
}
void pose_h_13(double *state, double *unused, double *out_1190906095138799015) {
  h_13(state, unused, out_1190906095138799015);
}
void pose_H_13(double *state, double *unused, double *out_2483513460486896264) {
  H_13(state, unused, out_2483513460486896264);
}
void pose_h_14(double *state, double *unused, double *out_4979926043979174598) {
  h_14(state, unused, out_4979926043979174598);
}
void pose_H_14(double *state, double *unused, double *out_8778575718114601361) {
  H_14(state, unused, out_8778575718114601361);
}
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
}

const EKF pose = {
  .name = "pose",
  .kinds = { 4, 10, 13, 14 },
  .feature_kinds = {  },
  .f_fun = pose_f_fun,
  .F_fun = pose_F_fun,
  .err_fun = pose_err_fun,
  .inv_err_fun = pose_inv_err_fun,
  .H_mod_fun = pose_H_mod_fun,
  .predict = pose_predict,
  .hs = {
    { 4, pose_h_4 },
    { 10, pose_h_10 },
    { 13, pose_h_13 },
    { 14, pose_h_14 },
  },
  .Hs = {
    { 4, pose_H_4 },
    { 10, pose_H_10 },
    { 13, pose_H_13 },
    { 14, pose_H_14 },
  },
  .updates = {
    { 4, pose_update_4 },
    { 10, pose_update_10 },
    { 13, pose_update_13 },
    { 14, pose_update_14 },
  },
  .Hes = {
  },
  .sets = {
  },
  .extra_routines = {
  },
};

ekf_lib_init(pose)
