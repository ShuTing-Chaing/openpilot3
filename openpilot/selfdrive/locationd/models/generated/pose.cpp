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
void err_fun(double *nom_x, double *delta_x, double *out_707370688016723266) {
   out_707370688016723266[0] = delta_x[0] + nom_x[0];
   out_707370688016723266[1] = delta_x[1] + nom_x[1];
   out_707370688016723266[2] = delta_x[2] + nom_x[2];
   out_707370688016723266[3] = delta_x[3] + nom_x[3];
   out_707370688016723266[4] = delta_x[4] + nom_x[4];
   out_707370688016723266[5] = delta_x[5] + nom_x[5];
   out_707370688016723266[6] = delta_x[6] + nom_x[6];
   out_707370688016723266[7] = delta_x[7] + nom_x[7];
   out_707370688016723266[8] = delta_x[8] + nom_x[8];
   out_707370688016723266[9] = delta_x[9] + nom_x[9];
   out_707370688016723266[10] = delta_x[10] + nom_x[10];
   out_707370688016723266[11] = delta_x[11] + nom_x[11];
   out_707370688016723266[12] = delta_x[12] + nom_x[12];
   out_707370688016723266[13] = delta_x[13] + nom_x[13];
   out_707370688016723266[14] = delta_x[14] + nom_x[14];
   out_707370688016723266[15] = delta_x[15] + nom_x[15];
   out_707370688016723266[16] = delta_x[16] + nom_x[16];
   out_707370688016723266[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_6651301100166098558) {
   out_6651301100166098558[0] = -nom_x[0] + true_x[0];
   out_6651301100166098558[1] = -nom_x[1] + true_x[1];
   out_6651301100166098558[2] = -nom_x[2] + true_x[2];
   out_6651301100166098558[3] = -nom_x[3] + true_x[3];
   out_6651301100166098558[4] = -nom_x[4] + true_x[4];
   out_6651301100166098558[5] = -nom_x[5] + true_x[5];
   out_6651301100166098558[6] = -nom_x[6] + true_x[6];
   out_6651301100166098558[7] = -nom_x[7] + true_x[7];
   out_6651301100166098558[8] = -nom_x[8] + true_x[8];
   out_6651301100166098558[9] = -nom_x[9] + true_x[9];
   out_6651301100166098558[10] = -nom_x[10] + true_x[10];
   out_6651301100166098558[11] = -nom_x[11] + true_x[11];
   out_6651301100166098558[12] = -nom_x[12] + true_x[12];
   out_6651301100166098558[13] = -nom_x[13] + true_x[13];
   out_6651301100166098558[14] = -nom_x[14] + true_x[14];
   out_6651301100166098558[15] = -nom_x[15] + true_x[15];
   out_6651301100166098558[16] = -nom_x[16] + true_x[16];
   out_6651301100166098558[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_95794323830548291) {
   out_95794323830548291[0] = 1.0;
   out_95794323830548291[1] = 0.0;
   out_95794323830548291[2] = 0.0;
   out_95794323830548291[3] = 0.0;
   out_95794323830548291[4] = 0.0;
   out_95794323830548291[5] = 0.0;
   out_95794323830548291[6] = 0.0;
   out_95794323830548291[7] = 0.0;
   out_95794323830548291[8] = 0.0;
   out_95794323830548291[9] = 0.0;
   out_95794323830548291[10] = 0.0;
   out_95794323830548291[11] = 0.0;
   out_95794323830548291[12] = 0.0;
   out_95794323830548291[13] = 0.0;
   out_95794323830548291[14] = 0.0;
   out_95794323830548291[15] = 0.0;
   out_95794323830548291[16] = 0.0;
   out_95794323830548291[17] = 0.0;
   out_95794323830548291[18] = 0.0;
   out_95794323830548291[19] = 1.0;
   out_95794323830548291[20] = 0.0;
   out_95794323830548291[21] = 0.0;
   out_95794323830548291[22] = 0.0;
   out_95794323830548291[23] = 0.0;
   out_95794323830548291[24] = 0.0;
   out_95794323830548291[25] = 0.0;
   out_95794323830548291[26] = 0.0;
   out_95794323830548291[27] = 0.0;
   out_95794323830548291[28] = 0.0;
   out_95794323830548291[29] = 0.0;
   out_95794323830548291[30] = 0.0;
   out_95794323830548291[31] = 0.0;
   out_95794323830548291[32] = 0.0;
   out_95794323830548291[33] = 0.0;
   out_95794323830548291[34] = 0.0;
   out_95794323830548291[35] = 0.0;
   out_95794323830548291[36] = 0.0;
   out_95794323830548291[37] = 0.0;
   out_95794323830548291[38] = 1.0;
   out_95794323830548291[39] = 0.0;
   out_95794323830548291[40] = 0.0;
   out_95794323830548291[41] = 0.0;
   out_95794323830548291[42] = 0.0;
   out_95794323830548291[43] = 0.0;
   out_95794323830548291[44] = 0.0;
   out_95794323830548291[45] = 0.0;
   out_95794323830548291[46] = 0.0;
   out_95794323830548291[47] = 0.0;
   out_95794323830548291[48] = 0.0;
   out_95794323830548291[49] = 0.0;
   out_95794323830548291[50] = 0.0;
   out_95794323830548291[51] = 0.0;
   out_95794323830548291[52] = 0.0;
   out_95794323830548291[53] = 0.0;
   out_95794323830548291[54] = 0.0;
   out_95794323830548291[55] = 0.0;
   out_95794323830548291[56] = 0.0;
   out_95794323830548291[57] = 1.0;
   out_95794323830548291[58] = 0.0;
   out_95794323830548291[59] = 0.0;
   out_95794323830548291[60] = 0.0;
   out_95794323830548291[61] = 0.0;
   out_95794323830548291[62] = 0.0;
   out_95794323830548291[63] = 0.0;
   out_95794323830548291[64] = 0.0;
   out_95794323830548291[65] = 0.0;
   out_95794323830548291[66] = 0.0;
   out_95794323830548291[67] = 0.0;
   out_95794323830548291[68] = 0.0;
   out_95794323830548291[69] = 0.0;
   out_95794323830548291[70] = 0.0;
   out_95794323830548291[71] = 0.0;
   out_95794323830548291[72] = 0.0;
   out_95794323830548291[73] = 0.0;
   out_95794323830548291[74] = 0.0;
   out_95794323830548291[75] = 0.0;
   out_95794323830548291[76] = 1.0;
   out_95794323830548291[77] = 0.0;
   out_95794323830548291[78] = 0.0;
   out_95794323830548291[79] = 0.0;
   out_95794323830548291[80] = 0.0;
   out_95794323830548291[81] = 0.0;
   out_95794323830548291[82] = 0.0;
   out_95794323830548291[83] = 0.0;
   out_95794323830548291[84] = 0.0;
   out_95794323830548291[85] = 0.0;
   out_95794323830548291[86] = 0.0;
   out_95794323830548291[87] = 0.0;
   out_95794323830548291[88] = 0.0;
   out_95794323830548291[89] = 0.0;
   out_95794323830548291[90] = 0.0;
   out_95794323830548291[91] = 0.0;
   out_95794323830548291[92] = 0.0;
   out_95794323830548291[93] = 0.0;
   out_95794323830548291[94] = 0.0;
   out_95794323830548291[95] = 1.0;
   out_95794323830548291[96] = 0.0;
   out_95794323830548291[97] = 0.0;
   out_95794323830548291[98] = 0.0;
   out_95794323830548291[99] = 0.0;
   out_95794323830548291[100] = 0.0;
   out_95794323830548291[101] = 0.0;
   out_95794323830548291[102] = 0.0;
   out_95794323830548291[103] = 0.0;
   out_95794323830548291[104] = 0.0;
   out_95794323830548291[105] = 0.0;
   out_95794323830548291[106] = 0.0;
   out_95794323830548291[107] = 0.0;
   out_95794323830548291[108] = 0.0;
   out_95794323830548291[109] = 0.0;
   out_95794323830548291[110] = 0.0;
   out_95794323830548291[111] = 0.0;
   out_95794323830548291[112] = 0.0;
   out_95794323830548291[113] = 0.0;
   out_95794323830548291[114] = 1.0;
   out_95794323830548291[115] = 0.0;
   out_95794323830548291[116] = 0.0;
   out_95794323830548291[117] = 0.0;
   out_95794323830548291[118] = 0.0;
   out_95794323830548291[119] = 0.0;
   out_95794323830548291[120] = 0.0;
   out_95794323830548291[121] = 0.0;
   out_95794323830548291[122] = 0.0;
   out_95794323830548291[123] = 0.0;
   out_95794323830548291[124] = 0.0;
   out_95794323830548291[125] = 0.0;
   out_95794323830548291[126] = 0.0;
   out_95794323830548291[127] = 0.0;
   out_95794323830548291[128] = 0.0;
   out_95794323830548291[129] = 0.0;
   out_95794323830548291[130] = 0.0;
   out_95794323830548291[131] = 0.0;
   out_95794323830548291[132] = 0.0;
   out_95794323830548291[133] = 1.0;
   out_95794323830548291[134] = 0.0;
   out_95794323830548291[135] = 0.0;
   out_95794323830548291[136] = 0.0;
   out_95794323830548291[137] = 0.0;
   out_95794323830548291[138] = 0.0;
   out_95794323830548291[139] = 0.0;
   out_95794323830548291[140] = 0.0;
   out_95794323830548291[141] = 0.0;
   out_95794323830548291[142] = 0.0;
   out_95794323830548291[143] = 0.0;
   out_95794323830548291[144] = 0.0;
   out_95794323830548291[145] = 0.0;
   out_95794323830548291[146] = 0.0;
   out_95794323830548291[147] = 0.0;
   out_95794323830548291[148] = 0.0;
   out_95794323830548291[149] = 0.0;
   out_95794323830548291[150] = 0.0;
   out_95794323830548291[151] = 0.0;
   out_95794323830548291[152] = 1.0;
   out_95794323830548291[153] = 0.0;
   out_95794323830548291[154] = 0.0;
   out_95794323830548291[155] = 0.0;
   out_95794323830548291[156] = 0.0;
   out_95794323830548291[157] = 0.0;
   out_95794323830548291[158] = 0.0;
   out_95794323830548291[159] = 0.0;
   out_95794323830548291[160] = 0.0;
   out_95794323830548291[161] = 0.0;
   out_95794323830548291[162] = 0.0;
   out_95794323830548291[163] = 0.0;
   out_95794323830548291[164] = 0.0;
   out_95794323830548291[165] = 0.0;
   out_95794323830548291[166] = 0.0;
   out_95794323830548291[167] = 0.0;
   out_95794323830548291[168] = 0.0;
   out_95794323830548291[169] = 0.0;
   out_95794323830548291[170] = 0.0;
   out_95794323830548291[171] = 1.0;
   out_95794323830548291[172] = 0.0;
   out_95794323830548291[173] = 0.0;
   out_95794323830548291[174] = 0.0;
   out_95794323830548291[175] = 0.0;
   out_95794323830548291[176] = 0.0;
   out_95794323830548291[177] = 0.0;
   out_95794323830548291[178] = 0.0;
   out_95794323830548291[179] = 0.0;
   out_95794323830548291[180] = 0.0;
   out_95794323830548291[181] = 0.0;
   out_95794323830548291[182] = 0.0;
   out_95794323830548291[183] = 0.0;
   out_95794323830548291[184] = 0.0;
   out_95794323830548291[185] = 0.0;
   out_95794323830548291[186] = 0.0;
   out_95794323830548291[187] = 0.0;
   out_95794323830548291[188] = 0.0;
   out_95794323830548291[189] = 0.0;
   out_95794323830548291[190] = 1.0;
   out_95794323830548291[191] = 0.0;
   out_95794323830548291[192] = 0.0;
   out_95794323830548291[193] = 0.0;
   out_95794323830548291[194] = 0.0;
   out_95794323830548291[195] = 0.0;
   out_95794323830548291[196] = 0.0;
   out_95794323830548291[197] = 0.0;
   out_95794323830548291[198] = 0.0;
   out_95794323830548291[199] = 0.0;
   out_95794323830548291[200] = 0.0;
   out_95794323830548291[201] = 0.0;
   out_95794323830548291[202] = 0.0;
   out_95794323830548291[203] = 0.0;
   out_95794323830548291[204] = 0.0;
   out_95794323830548291[205] = 0.0;
   out_95794323830548291[206] = 0.0;
   out_95794323830548291[207] = 0.0;
   out_95794323830548291[208] = 0.0;
   out_95794323830548291[209] = 1.0;
   out_95794323830548291[210] = 0.0;
   out_95794323830548291[211] = 0.0;
   out_95794323830548291[212] = 0.0;
   out_95794323830548291[213] = 0.0;
   out_95794323830548291[214] = 0.0;
   out_95794323830548291[215] = 0.0;
   out_95794323830548291[216] = 0.0;
   out_95794323830548291[217] = 0.0;
   out_95794323830548291[218] = 0.0;
   out_95794323830548291[219] = 0.0;
   out_95794323830548291[220] = 0.0;
   out_95794323830548291[221] = 0.0;
   out_95794323830548291[222] = 0.0;
   out_95794323830548291[223] = 0.0;
   out_95794323830548291[224] = 0.0;
   out_95794323830548291[225] = 0.0;
   out_95794323830548291[226] = 0.0;
   out_95794323830548291[227] = 0.0;
   out_95794323830548291[228] = 1.0;
   out_95794323830548291[229] = 0.0;
   out_95794323830548291[230] = 0.0;
   out_95794323830548291[231] = 0.0;
   out_95794323830548291[232] = 0.0;
   out_95794323830548291[233] = 0.0;
   out_95794323830548291[234] = 0.0;
   out_95794323830548291[235] = 0.0;
   out_95794323830548291[236] = 0.0;
   out_95794323830548291[237] = 0.0;
   out_95794323830548291[238] = 0.0;
   out_95794323830548291[239] = 0.0;
   out_95794323830548291[240] = 0.0;
   out_95794323830548291[241] = 0.0;
   out_95794323830548291[242] = 0.0;
   out_95794323830548291[243] = 0.0;
   out_95794323830548291[244] = 0.0;
   out_95794323830548291[245] = 0.0;
   out_95794323830548291[246] = 0.0;
   out_95794323830548291[247] = 1.0;
   out_95794323830548291[248] = 0.0;
   out_95794323830548291[249] = 0.0;
   out_95794323830548291[250] = 0.0;
   out_95794323830548291[251] = 0.0;
   out_95794323830548291[252] = 0.0;
   out_95794323830548291[253] = 0.0;
   out_95794323830548291[254] = 0.0;
   out_95794323830548291[255] = 0.0;
   out_95794323830548291[256] = 0.0;
   out_95794323830548291[257] = 0.0;
   out_95794323830548291[258] = 0.0;
   out_95794323830548291[259] = 0.0;
   out_95794323830548291[260] = 0.0;
   out_95794323830548291[261] = 0.0;
   out_95794323830548291[262] = 0.0;
   out_95794323830548291[263] = 0.0;
   out_95794323830548291[264] = 0.0;
   out_95794323830548291[265] = 0.0;
   out_95794323830548291[266] = 1.0;
   out_95794323830548291[267] = 0.0;
   out_95794323830548291[268] = 0.0;
   out_95794323830548291[269] = 0.0;
   out_95794323830548291[270] = 0.0;
   out_95794323830548291[271] = 0.0;
   out_95794323830548291[272] = 0.0;
   out_95794323830548291[273] = 0.0;
   out_95794323830548291[274] = 0.0;
   out_95794323830548291[275] = 0.0;
   out_95794323830548291[276] = 0.0;
   out_95794323830548291[277] = 0.0;
   out_95794323830548291[278] = 0.0;
   out_95794323830548291[279] = 0.0;
   out_95794323830548291[280] = 0.0;
   out_95794323830548291[281] = 0.0;
   out_95794323830548291[282] = 0.0;
   out_95794323830548291[283] = 0.0;
   out_95794323830548291[284] = 0.0;
   out_95794323830548291[285] = 1.0;
   out_95794323830548291[286] = 0.0;
   out_95794323830548291[287] = 0.0;
   out_95794323830548291[288] = 0.0;
   out_95794323830548291[289] = 0.0;
   out_95794323830548291[290] = 0.0;
   out_95794323830548291[291] = 0.0;
   out_95794323830548291[292] = 0.0;
   out_95794323830548291[293] = 0.0;
   out_95794323830548291[294] = 0.0;
   out_95794323830548291[295] = 0.0;
   out_95794323830548291[296] = 0.0;
   out_95794323830548291[297] = 0.0;
   out_95794323830548291[298] = 0.0;
   out_95794323830548291[299] = 0.0;
   out_95794323830548291[300] = 0.0;
   out_95794323830548291[301] = 0.0;
   out_95794323830548291[302] = 0.0;
   out_95794323830548291[303] = 0.0;
   out_95794323830548291[304] = 1.0;
   out_95794323830548291[305] = 0.0;
   out_95794323830548291[306] = 0.0;
   out_95794323830548291[307] = 0.0;
   out_95794323830548291[308] = 0.0;
   out_95794323830548291[309] = 0.0;
   out_95794323830548291[310] = 0.0;
   out_95794323830548291[311] = 0.0;
   out_95794323830548291[312] = 0.0;
   out_95794323830548291[313] = 0.0;
   out_95794323830548291[314] = 0.0;
   out_95794323830548291[315] = 0.0;
   out_95794323830548291[316] = 0.0;
   out_95794323830548291[317] = 0.0;
   out_95794323830548291[318] = 0.0;
   out_95794323830548291[319] = 0.0;
   out_95794323830548291[320] = 0.0;
   out_95794323830548291[321] = 0.0;
   out_95794323830548291[322] = 0.0;
   out_95794323830548291[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_5629211650094912184) {
   out_5629211650094912184[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_5629211650094912184[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_5629211650094912184[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_5629211650094912184[3] = dt*state[12] + state[3];
   out_5629211650094912184[4] = dt*state[13] + state[4];
   out_5629211650094912184[5] = dt*state[14] + state[5];
   out_5629211650094912184[6] = state[6];
   out_5629211650094912184[7] = state[7];
   out_5629211650094912184[8] = state[8];
   out_5629211650094912184[9] = state[9];
   out_5629211650094912184[10] = state[10];
   out_5629211650094912184[11] = state[11];
   out_5629211650094912184[12] = state[12];
   out_5629211650094912184[13] = state[13];
   out_5629211650094912184[14] = state[14];
   out_5629211650094912184[15] = state[15];
   out_5629211650094912184[16] = state[16];
   out_5629211650094912184[17] = state[17];
}
void F_fun(double *state, double dt, double *out_5949544175274232713) {
   out_5949544175274232713[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5949544175274232713[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5949544175274232713[2] = 0;
   out_5949544175274232713[3] = 0;
   out_5949544175274232713[4] = 0;
   out_5949544175274232713[5] = 0;
   out_5949544175274232713[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5949544175274232713[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5949544175274232713[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5949544175274232713[9] = 0;
   out_5949544175274232713[10] = 0;
   out_5949544175274232713[11] = 0;
   out_5949544175274232713[12] = 0;
   out_5949544175274232713[13] = 0;
   out_5949544175274232713[14] = 0;
   out_5949544175274232713[15] = 0;
   out_5949544175274232713[16] = 0;
   out_5949544175274232713[17] = 0;
   out_5949544175274232713[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_5949544175274232713[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_5949544175274232713[20] = 0;
   out_5949544175274232713[21] = 0;
   out_5949544175274232713[22] = 0;
   out_5949544175274232713[23] = 0;
   out_5949544175274232713[24] = 0;
   out_5949544175274232713[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_5949544175274232713[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_5949544175274232713[27] = 0;
   out_5949544175274232713[28] = 0;
   out_5949544175274232713[29] = 0;
   out_5949544175274232713[30] = 0;
   out_5949544175274232713[31] = 0;
   out_5949544175274232713[32] = 0;
   out_5949544175274232713[33] = 0;
   out_5949544175274232713[34] = 0;
   out_5949544175274232713[35] = 0;
   out_5949544175274232713[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5949544175274232713[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5949544175274232713[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5949544175274232713[39] = 0;
   out_5949544175274232713[40] = 0;
   out_5949544175274232713[41] = 0;
   out_5949544175274232713[42] = 0;
   out_5949544175274232713[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5949544175274232713[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5949544175274232713[45] = 0;
   out_5949544175274232713[46] = 0;
   out_5949544175274232713[47] = 0;
   out_5949544175274232713[48] = 0;
   out_5949544175274232713[49] = 0;
   out_5949544175274232713[50] = 0;
   out_5949544175274232713[51] = 0;
   out_5949544175274232713[52] = 0;
   out_5949544175274232713[53] = 0;
   out_5949544175274232713[54] = 0;
   out_5949544175274232713[55] = 0;
   out_5949544175274232713[56] = 0;
   out_5949544175274232713[57] = 1;
   out_5949544175274232713[58] = 0;
   out_5949544175274232713[59] = 0;
   out_5949544175274232713[60] = 0;
   out_5949544175274232713[61] = 0;
   out_5949544175274232713[62] = 0;
   out_5949544175274232713[63] = 0;
   out_5949544175274232713[64] = 0;
   out_5949544175274232713[65] = 0;
   out_5949544175274232713[66] = dt;
   out_5949544175274232713[67] = 0;
   out_5949544175274232713[68] = 0;
   out_5949544175274232713[69] = 0;
   out_5949544175274232713[70] = 0;
   out_5949544175274232713[71] = 0;
   out_5949544175274232713[72] = 0;
   out_5949544175274232713[73] = 0;
   out_5949544175274232713[74] = 0;
   out_5949544175274232713[75] = 0;
   out_5949544175274232713[76] = 1;
   out_5949544175274232713[77] = 0;
   out_5949544175274232713[78] = 0;
   out_5949544175274232713[79] = 0;
   out_5949544175274232713[80] = 0;
   out_5949544175274232713[81] = 0;
   out_5949544175274232713[82] = 0;
   out_5949544175274232713[83] = 0;
   out_5949544175274232713[84] = 0;
   out_5949544175274232713[85] = dt;
   out_5949544175274232713[86] = 0;
   out_5949544175274232713[87] = 0;
   out_5949544175274232713[88] = 0;
   out_5949544175274232713[89] = 0;
   out_5949544175274232713[90] = 0;
   out_5949544175274232713[91] = 0;
   out_5949544175274232713[92] = 0;
   out_5949544175274232713[93] = 0;
   out_5949544175274232713[94] = 0;
   out_5949544175274232713[95] = 1;
   out_5949544175274232713[96] = 0;
   out_5949544175274232713[97] = 0;
   out_5949544175274232713[98] = 0;
   out_5949544175274232713[99] = 0;
   out_5949544175274232713[100] = 0;
   out_5949544175274232713[101] = 0;
   out_5949544175274232713[102] = 0;
   out_5949544175274232713[103] = 0;
   out_5949544175274232713[104] = dt;
   out_5949544175274232713[105] = 0;
   out_5949544175274232713[106] = 0;
   out_5949544175274232713[107] = 0;
   out_5949544175274232713[108] = 0;
   out_5949544175274232713[109] = 0;
   out_5949544175274232713[110] = 0;
   out_5949544175274232713[111] = 0;
   out_5949544175274232713[112] = 0;
   out_5949544175274232713[113] = 0;
   out_5949544175274232713[114] = 1;
   out_5949544175274232713[115] = 0;
   out_5949544175274232713[116] = 0;
   out_5949544175274232713[117] = 0;
   out_5949544175274232713[118] = 0;
   out_5949544175274232713[119] = 0;
   out_5949544175274232713[120] = 0;
   out_5949544175274232713[121] = 0;
   out_5949544175274232713[122] = 0;
   out_5949544175274232713[123] = 0;
   out_5949544175274232713[124] = 0;
   out_5949544175274232713[125] = 0;
   out_5949544175274232713[126] = 0;
   out_5949544175274232713[127] = 0;
   out_5949544175274232713[128] = 0;
   out_5949544175274232713[129] = 0;
   out_5949544175274232713[130] = 0;
   out_5949544175274232713[131] = 0;
   out_5949544175274232713[132] = 0;
   out_5949544175274232713[133] = 1;
   out_5949544175274232713[134] = 0;
   out_5949544175274232713[135] = 0;
   out_5949544175274232713[136] = 0;
   out_5949544175274232713[137] = 0;
   out_5949544175274232713[138] = 0;
   out_5949544175274232713[139] = 0;
   out_5949544175274232713[140] = 0;
   out_5949544175274232713[141] = 0;
   out_5949544175274232713[142] = 0;
   out_5949544175274232713[143] = 0;
   out_5949544175274232713[144] = 0;
   out_5949544175274232713[145] = 0;
   out_5949544175274232713[146] = 0;
   out_5949544175274232713[147] = 0;
   out_5949544175274232713[148] = 0;
   out_5949544175274232713[149] = 0;
   out_5949544175274232713[150] = 0;
   out_5949544175274232713[151] = 0;
   out_5949544175274232713[152] = 1;
   out_5949544175274232713[153] = 0;
   out_5949544175274232713[154] = 0;
   out_5949544175274232713[155] = 0;
   out_5949544175274232713[156] = 0;
   out_5949544175274232713[157] = 0;
   out_5949544175274232713[158] = 0;
   out_5949544175274232713[159] = 0;
   out_5949544175274232713[160] = 0;
   out_5949544175274232713[161] = 0;
   out_5949544175274232713[162] = 0;
   out_5949544175274232713[163] = 0;
   out_5949544175274232713[164] = 0;
   out_5949544175274232713[165] = 0;
   out_5949544175274232713[166] = 0;
   out_5949544175274232713[167] = 0;
   out_5949544175274232713[168] = 0;
   out_5949544175274232713[169] = 0;
   out_5949544175274232713[170] = 0;
   out_5949544175274232713[171] = 1;
   out_5949544175274232713[172] = 0;
   out_5949544175274232713[173] = 0;
   out_5949544175274232713[174] = 0;
   out_5949544175274232713[175] = 0;
   out_5949544175274232713[176] = 0;
   out_5949544175274232713[177] = 0;
   out_5949544175274232713[178] = 0;
   out_5949544175274232713[179] = 0;
   out_5949544175274232713[180] = 0;
   out_5949544175274232713[181] = 0;
   out_5949544175274232713[182] = 0;
   out_5949544175274232713[183] = 0;
   out_5949544175274232713[184] = 0;
   out_5949544175274232713[185] = 0;
   out_5949544175274232713[186] = 0;
   out_5949544175274232713[187] = 0;
   out_5949544175274232713[188] = 0;
   out_5949544175274232713[189] = 0;
   out_5949544175274232713[190] = 1;
   out_5949544175274232713[191] = 0;
   out_5949544175274232713[192] = 0;
   out_5949544175274232713[193] = 0;
   out_5949544175274232713[194] = 0;
   out_5949544175274232713[195] = 0;
   out_5949544175274232713[196] = 0;
   out_5949544175274232713[197] = 0;
   out_5949544175274232713[198] = 0;
   out_5949544175274232713[199] = 0;
   out_5949544175274232713[200] = 0;
   out_5949544175274232713[201] = 0;
   out_5949544175274232713[202] = 0;
   out_5949544175274232713[203] = 0;
   out_5949544175274232713[204] = 0;
   out_5949544175274232713[205] = 0;
   out_5949544175274232713[206] = 0;
   out_5949544175274232713[207] = 0;
   out_5949544175274232713[208] = 0;
   out_5949544175274232713[209] = 1;
   out_5949544175274232713[210] = 0;
   out_5949544175274232713[211] = 0;
   out_5949544175274232713[212] = 0;
   out_5949544175274232713[213] = 0;
   out_5949544175274232713[214] = 0;
   out_5949544175274232713[215] = 0;
   out_5949544175274232713[216] = 0;
   out_5949544175274232713[217] = 0;
   out_5949544175274232713[218] = 0;
   out_5949544175274232713[219] = 0;
   out_5949544175274232713[220] = 0;
   out_5949544175274232713[221] = 0;
   out_5949544175274232713[222] = 0;
   out_5949544175274232713[223] = 0;
   out_5949544175274232713[224] = 0;
   out_5949544175274232713[225] = 0;
   out_5949544175274232713[226] = 0;
   out_5949544175274232713[227] = 0;
   out_5949544175274232713[228] = 1;
   out_5949544175274232713[229] = 0;
   out_5949544175274232713[230] = 0;
   out_5949544175274232713[231] = 0;
   out_5949544175274232713[232] = 0;
   out_5949544175274232713[233] = 0;
   out_5949544175274232713[234] = 0;
   out_5949544175274232713[235] = 0;
   out_5949544175274232713[236] = 0;
   out_5949544175274232713[237] = 0;
   out_5949544175274232713[238] = 0;
   out_5949544175274232713[239] = 0;
   out_5949544175274232713[240] = 0;
   out_5949544175274232713[241] = 0;
   out_5949544175274232713[242] = 0;
   out_5949544175274232713[243] = 0;
   out_5949544175274232713[244] = 0;
   out_5949544175274232713[245] = 0;
   out_5949544175274232713[246] = 0;
   out_5949544175274232713[247] = 1;
   out_5949544175274232713[248] = 0;
   out_5949544175274232713[249] = 0;
   out_5949544175274232713[250] = 0;
   out_5949544175274232713[251] = 0;
   out_5949544175274232713[252] = 0;
   out_5949544175274232713[253] = 0;
   out_5949544175274232713[254] = 0;
   out_5949544175274232713[255] = 0;
   out_5949544175274232713[256] = 0;
   out_5949544175274232713[257] = 0;
   out_5949544175274232713[258] = 0;
   out_5949544175274232713[259] = 0;
   out_5949544175274232713[260] = 0;
   out_5949544175274232713[261] = 0;
   out_5949544175274232713[262] = 0;
   out_5949544175274232713[263] = 0;
   out_5949544175274232713[264] = 0;
   out_5949544175274232713[265] = 0;
   out_5949544175274232713[266] = 1;
   out_5949544175274232713[267] = 0;
   out_5949544175274232713[268] = 0;
   out_5949544175274232713[269] = 0;
   out_5949544175274232713[270] = 0;
   out_5949544175274232713[271] = 0;
   out_5949544175274232713[272] = 0;
   out_5949544175274232713[273] = 0;
   out_5949544175274232713[274] = 0;
   out_5949544175274232713[275] = 0;
   out_5949544175274232713[276] = 0;
   out_5949544175274232713[277] = 0;
   out_5949544175274232713[278] = 0;
   out_5949544175274232713[279] = 0;
   out_5949544175274232713[280] = 0;
   out_5949544175274232713[281] = 0;
   out_5949544175274232713[282] = 0;
   out_5949544175274232713[283] = 0;
   out_5949544175274232713[284] = 0;
   out_5949544175274232713[285] = 1;
   out_5949544175274232713[286] = 0;
   out_5949544175274232713[287] = 0;
   out_5949544175274232713[288] = 0;
   out_5949544175274232713[289] = 0;
   out_5949544175274232713[290] = 0;
   out_5949544175274232713[291] = 0;
   out_5949544175274232713[292] = 0;
   out_5949544175274232713[293] = 0;
   out_5949544175274232713[294] = 0;
   out_5949544175274232713[295] = 0;
   out_5949544175274232713[296] = 0;
   out_5949544175274232713[297] = 0;
   out_5949544175274232713[298] = 0;
   out_5949544175274232713[299] = 0;
   out_5949544175274232713[300] = 0;
   out_5949544175274232713[301] = 0;
   out_5949544175274232713[302] = 0;
   out_5949544175274232713[303] = 0;
   out_5949544175274232713[304] = 1;
   out_5949544175274232713[305] = 0;
   out_5949544175274232713[306] = 0;
   out_5949544175274232713[307] = 0;
   out_5949544175274232713[308] = 0;
   out_5949544175274232713[309] = 0;
   out_5949544175274232713[310] = 0;
   out_5949544175274232713[311] = 0;
   out_5949544175274232713[312] = 0;
   out_5949544175274232713[313] = 0;
   out_5949544175274232713[314] = 0;
   out_5949544175274232713[315] = 0;
   out_5949544175274232713[316] = 0;
   out_5949544175274232713[317] = 0;
   out_5949544175274232713[318] = 0;
   out_5949544175274232713[319] = 0;
   out_5949544175274232713[320] = 0;
   out_5949544175274232713[321] = 0;
   out_5949544175274232713[322] = 0;
   out_5949544175274232713[323] = 1;
}
void h_4(double *state, double *unused, double *out_4850019821057066741) {
   out_4850019821057066741[0] = state[6] + state[9];
   out_4850019821057066741[1] = state[7] + state[10];
   out_4850019821057066741[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_9040155989888369633) {
   out_9040155989888369633[0] = 0;
   out_9040155989888369633[1] = 0;
   out_9040155989888369633[2] = 0;
   out_9040155989888369633[3] = 0;
   out_9040155989888369633[4] = 0;
   out_9040155989888369633[5] = 0;
   out_9040155989888369633[6] = 1;
   out_9040155989888369633[7] = 0;
   out_9040155989888369633[8] = 0;
   out_9040155989888369633[9] = 1;
   out_9040155989888369633[10] = 0;
   out_9040155989888369633[11] = 0;
   out_9040155989888369633[12] = 0;
   out_9040155989888369633[13] = 0;
   out_9040155989888369633[14] = 0;
   out_9040155989888369633[15] = 0;
   out_9040155989888369633[16] = 0;
   out_9040155989888369633[17] = 0;
   out_9040155989888369633[18] = 0;
   out_9040155989888369633[19] = 0;
   out_9040155989888369633[20] = 0;
   out_9040155989888369633[21] = 0;
   out_9040155989888369633[22] = 0;
   out_9040155989888369633[23] = 0;
   out_9040155989888369633[24] = 0;
   out_9040155989888369633[25] = 1;
   out_9040155989888369633[26] = 0;
   out_9040155989888369633[27] = 0;
   out_9040155989888369633[28] = 1;
   out_9040155989888369633[29] = 0;
   out_9040155989888369633[30] = 0;
   out_9040155989888369633[31] = 0;
   out_9040155989888369633[32] = 0;
   out_9040155989888369633[33] = 0;
   out_9040155989888369633[34] = 0;
   out_9040155989888369633[35] = 0;
   out_9040155989888369633[36] = 0;
   out_9040155989888369633[37] = 0;
   out_9040155989888369633[38] = 0;
   out_9040155989888369633[39] = 0;
   out_9040155989888369633[40] = 0;
   out_9040155989888369633[41] = 0;
   out_9040155989888369633[42] = 0;
   out_9040155989888369633[43] = 0;
   out_9040155989888369633[44] = 1;
   out_9040155989888369633[45] = 0;
   out_9040155989888369633[46] = 0;
   out_9040155989888369633[47] = 1;
   out_9040155989888369633[48] = 0;
   out_9040155989888369633[49] = 0;
   out_9040155989888369633[50] = 0;
   out_9040155989888369633[51] = 0;
   out_9040155989888369633[52] = 0;
   out_9040155989888369633[53] = 0;
}
void h_10(double *state, double *unused, double *out_9215908307232531236) {
   out_9215908307232531236[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_9215908307232531236[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_9215908307232531236[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_1931647352710355575) {
   out_1931647352710355575[0] = 0;
   out_1931647352710355575[1] = 9.8100000000000005*cos(state[1]);
   out_1931647352710355575[2] = 0;
   out_1931647352710355575[3] = 0;
   out_1931647352710355575[4] = -state[8];
   out_1931647352710355575[5] = state[7];
   out_1931647352710355575[6] = 0;
   out_1931647352710355575[7] = state[5];
   out_1931647352710355575[8] = -state[4];
   out_1931647352710355575[9] = 0;
   out_1931647352710355575[10] = 0;
   out_1931647352710355575[11] = 0;
   out_1931647352710355575[12] = 1;
   out_1931647352710355575[13] = 0;
   out_1931647352710355575[14] = 0;
   out_1931647352710355575[15] = 1;
   out_1931647352710355575[16] = 0;
   out_1931647352710355575[17] = 0;
   out_1931647352710355575[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_1931647352710355575[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_1931647352710355575[20] = 0;
   out_1931647352710355575[21] = state[8];
   out_1931647352710355575[22] = 0;
   out_1931647352710355575[23] = -state[6];
   out_1931647352710355575[24] = -state[5];
   out_1931647352710355575[25] = 0;
   out_1931647352710355575[26] = state[3];
   out_1931647352710355575[27] = 0;
   out_1931647352710355575[28] = 0;
   out_1931647352710355575[29] = 0;
   out_1931647352710355575[30] = 0;
   out_1931647352710355575[31] = 1;
   out_1931647352710355575[32] = 0;
   out_1931647352710355575[33] = 0;
   out_1931647352710355575[34] = 1;
   out_1931647352710355575[35] = 0;
   out_1931647352710355575[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_1931647352710355575[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_1931647352710355575[38] = 0;
   out_1931647352710355575[39] = -state[7];
   out_1931647352710355575[40] = state[6];
   out_1931647352710355575[41] = 0;
   out_1931647352710355575[42] = state[4];
   out_1931647352710355575[43] = -state[3];
   out_1931647352710355575[44] = 0;
   out_1931647352710355575[45] = 0;
   out_1931647352710355575[46] = 0;
   out_1931647352710355575[47] = 0;
   out_1931647352710355575[48] = 0;
   out_1931647352710355575[49] = 0;
   out_1931647352710355575[50] = 1;
   out_1931647352710355575[51] = 0;
   out_1931647352710355575[52] = 0;
   out_1931647352710355575[53] = 1;
}
void h_13(double *state, double *unused, double *out_246971447327183336) {
   out_246971447327183336[0] = state[3];
   out_246971447327183336[1] = state[4];
   out_246971447327183336[2] = state[5];
}
void H_13(double *state, double *unused, double *out_5827882164556036832) {
   out_5827882164556036832[0] = 0;
   out_5827882164556036832[1] = 0;
   out_5827882164556036832[2] = 0;
   out_5827882164556036832[3] = 1;
   out_5827882164556036832[4] = 0;
   out_5827882164556036832[5] = 0;
   out_5827882164556036832[6] = 0;
   out_5827882164556036832[7] = 0;
   out_5827882164556036832[8] = 0;
   out_5827882164556036832[9] = 0;
   out_5827882164556036832[10] = 0;
   out_5827882164556036832[11] = 0;
   out_5827882164556036832[12] = 0;
   out_5827882164556036832[13] = 0;
   out_5827882164556036832[14] = 0;
   out_5827882164556036832[15] = 0;
   out_5827882164556036832[16] = 0;
   out_5827882164556036832[17] = 0;
   out_5827882164556036832[18] = 0;
   out_5827882164556036832[19] = 0;
   out_5827882164556036832[20] = 0;
   out_5827882164556036832[21] = 0;
   out_5827882164556036832[22] = 1;
   out_5827882164556036832[23] = 0;
   out_5827882164556036832[24] = 0;
   out_5827882164556036832[25] = 0;
   out_5827882164556036832[26] = 0;
   out_5827882164556036832[27] = 0;
   out_5827882164556036832[28] = 0;
   out_5827882164556036832[29] = 0;
   out_5827882164556036832[30] = 0;
   out_5827882164556036832[31] = 0;
   out_5827882164556036832[32] = 0;
   out_5827882164556036832[33] = 0;
   out_5827882164556036832[34] = 0;
   out_5827882164556036832[35] = 0;
   out_5827882164556036832[36] = 0;
   out_5827882164556036832[37] = 0;
   out_5827882164556036832[38] = 0;
   out_5827882164556036832[39] = 0;
   out_5827882164556036832[40] = 0;
   out_5827882164556036832[41] = 1;
   out_5827882164556036832[42] = 0;
   out_5827882164556036832[43] = 0;
   out_5827882164556036832[44] = 0;
   out_5827882164556036832[45] = 0;
   out_5827882164556036832[46] = 0;
   out_5827882164556036832[47] = 0;
   out_5827882164556036832[48] = 0;
   out_5827882164556036832[49] = 0;
   out_5827882164556036832[50] = 0;
   out_5827882164556036832[51] = 0;
   out_5827882164556036832[52] = 0;
   out_5827882164556036832[53] = 0;
}
void h_14(double *state, double *unused, double *out_3722913904389418623) {
   out_3722913904389418623[0] = state[6];
   out_3722913904389418623[1] = state[7];
   out_3722913904389418623[2] = state[8];
}
void H_14(double *state, double *unused, double *out_5076915133548885104) {
   out_5076915133548885104[0] = 0;
   out_5076915133548885104[1] = 0;
   out_5076915133548885104[2] = 0;
   out_5076915133548885104[3] = 0;
   out_5076915133548885104[4] = 0;
   out_5076915133548885104[5] = 0;
   out_5076915133548885104[6] = 1;
   out_5076915133548885104[7] = 0;
   out_5076915133548885104[8] = 0;
   out_5076915133548885104[9] = 0;
   out_5076915133548885104[10] = 0;
   out_5076915133548885104[11] = 0;
   out_5076915133548885104[12] = 0;
   out_5076915133548885104[13] = 0;
   out_5076915133548885104[14] = 0;
   out_5076915133548885104[15] = 0;
   out_5076915133548885104[16] = 0;
   out_5076915133548885104[17] = 0;
   out_5076915133548885104[18] = 0;
   out_5076915133548885104[19] = 0;
   out_5076915133548885104[20] = 0;
   out_5076915133548885104[21] = 0;
   out_5076915133548885104[22] = 0;
   out_5076915133548885104[23] = 0;
   out_5076915133548885104[24] = 0;
   out_5076915133548885104[25] = 1;
   out_5076915133548885104[26] = 0;
   out_5076915133548885104[27] = 0;
   out_5076915133548885104[28] = 0;
   out_5076915133548885104[29] = 0;
   out_5076915133548885104[30] = 0;
   out_5076915133548885104[31] = 0;
   out_5076915133548885104[32] = 0;
   out_5076915133548885104[33] = 0;
   out_5076915133548885104[34] = 0;
   out_5076915133548885104[35] = 0;
   out_5076915133548885104[36] = 0;
   out_5076915133548885104[37] = 0;
   out_5076915133548885104[38] = 0;
   out_5076915133548885104[39] = 0;
   out_5076915133548885104[40] = 0;
   out_5076915133548885104[41] = 0;
   out_5076915133548885104[42] = 0;
   out_5076915133548885104[43] = 0;
   out_5076915133548885104[44] = 1;
   out_5076915133548885104[45] = 0;
   out_5076915133548885104[46] = 0;
   out_5076915133548885104[47] = 0;
   out_5076915133548885104[48] = 0;
   out_5076915133548885104[49] = 0;
   out_5076915133548885104[50] = 0;
   out_5076915133548885104[51] = 0;
   out_5076915133548885104[52] = 0;
   out_5076915133548885104[53] = 0;
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
void pose_err_fun(double *nom_x, double *delta_x, double *out_707370688016723266) {
  err_fun(nom_x, delta_x, out_707370688016723266);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_6651301100166098558) {
  inv_err_fun(nom_x, true_x, out_6651301100166098558);
}
void pose_H_mod_fun(double *state, double *out_95794323830548291) {
  H_mod_fun(state, out_95794323830548291);
}
void pose_f_fun(double *state, double dt, double *out_5629211650094912184) {
  f_fun(state,  dt, out_5629211650094912184);
}
void pose_F_fun(double *state, double dt, double *out_5949544175274232713) {
  F_fun(state,  dt, out_5949544175274232713);
}
void pose_h_4(double *state, double *unused, double *out_4850019821057066741) {
  h_4(state, unused, out_4850019821057066741);
}
void pose_H_4(double *state, double *unused, double *out_9040155989888369633) {
  H_4(state, unused, out_9040155989888369633);
}
void pose_h_10(double *state, double *unused, double *out_9215908307232531236) {
  h_10(state, unused, out_9215908307232531236);
}
void pose_H_10(double *state, double *unused, double *out_1931647352710355575) {
  H_10(state, unused, out_1931647352710355575);
}
void pose_h_13(double *state, double *unused, double *out_246971447327183336) {
  h_13(state, unused, out_246971447327183336);
}
void pose_H_13(double *state, double *unused, double *out_5827882164556036832) {
  H_13(state, unused, out_5827882164556036832);
}
void pose_h_14(double *state, double *unused, double *out_3722913904389418623) {
  h_14(state, unused, out_3722913904389418623);
}
void pose_H_14(double *state, double *unused, double *out_5076915133548885104) {
  H_14(state, unused, out_5076915133548885104);
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
